import asyncio
import logging
import os
import random
import time
from io import BytesIO
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton, InputFile
from telegram.constants import ChatAction
from telegram.ext import (
    Application, ApplicationHandlerStop, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, TypeHandler, filters,
)

from .config import Settings
from .image_utils import validate_image, prepare_image_for_analysis
from .preferences import PreferenceStore
from .operations import OperationsStore
from .providers.gemini import GeminiVisionProvider
from .key_store import GeminiKeyStore
from .messages import build_welcome_message, fit_telegram_text, format_prompt_message

logger = logging.getLogger(__name__)
OUTPUT_MODES = {"natural": "Natural", "tags": "Tags", "enhanced": "Enhanced"}
DETAIL_LEVELS = {"quick": "Quick", "standard": "Standard", "detailed": "Detailed", "maximum": "Maximum"}
LANGUAGES = {"English": "English", "Hindi": "Hindi", "Hinglish": "Hinglish"}

WELCOME_IMAGE = Path(__file__).resolve().parent / "assets" / "welcome.jpg"


def get_provider(context: ContextTypes.DEFAULT_TYPE) -> GeminiVisionProvider:
    return context.application.bot_data["provider"]


def get_settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


def get_preferences(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> dict[str, str]:
    return context.application.bot_data["preferences"].get(user_id)


def get_operations(context: ContextTypes.DEFAULT_TYPE) -> OperationsStore:
    return context.application.bot_data["operations"]


async def db_call(func, *args, **kwargs):
    """Run synchronous SQLite/Mongo work away from Telegram's async event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def schedule_mongo_sync(context, user_id: int, username: str, first_name: str, last_name: str) -> None:
    store = get_operations(context)
    if store.mongo_users is not None:
        task = asyncio.create_task(db_call(store.sync_mongo_user, user_id, username, first_name, last_name))
        task.add_done_callback(lambda done: logger.warning("Mongo user sync failed: %s", done.exception())
                               if not done.cancelled() and done.exception() else None)


async def check_usage(context: ContextTypes.DEFAULT_TYPE, user_id: int, cooldown_seconds: int | None = None) -> tuple[bool, str]:
    settings = get_settings(context)
    cooldown = settings.request_cooldown_seconds if cooldown_seconds is None else cooldown_seconds
    return await db_call(
        get_operations(context).allow_request, user_id,
        cooldown_seconds=cooldown, user_daily_limit=settings.user_daily_limit,
        global_daily_limit=settings.global_daily_limit,
    )


def is_retryable_ai_error(error: Exception) -> bool:
    message = str(error).lower()
    retry_markers = (
        "503", "502", "500", "504", "429", "408", "resource_exhausted",
        "temporarily unavailable", "service unavailable", "internal server error",
        "deadline exceeded", "timed out", "timeout", "connection reset",
        "connection error", "network is unreachable",
    )
    return any(marker in message for marker in retry_markers)


async def run_ai_with_retry(context, func, *args):
    settings = get_settings(context)
    semaphore = context.application.bot_data["ai_semaphore"]
    async with semaphore:
        for attempt in range(settings.ai_max_retries + 1):
            try:
                return await asyncio.to_thread(func, *args)
            except Exception as error:
                if attempt >= settings.ai_max_retries or not is_retryable_ai_error(error):
                    raise
                # Keep recovery responsive; a long backoff can make image requests
                # feel stalled. Retry count remains configurable via AI_MAX_RETRIES.
                delay = min(3.0, (0.8 * (2 ** attempt)) + random.uniform(0, 0.2))
                logger.warning("Transient Gemini error; retry %s/%s in %.2fs: %s",
                               attempt + 1, settings.ai_max_retries, delay, type(error).__name__)
                await asyncio.sleep(delay)


def settings_keyboard(prefs: dict[str, str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(("✓ " if prefs["output_mode"] == key else "") + label,
                              callback_data=f"set:mode:{key}") for key, label in OUTPUT_MODES.items()],
        [InlineKeyboardButton(("✓ " if prefs["detail_level"] == key else "") + label,
                              callback_data=f"set:detail:{key}") for key, label in DETAIL_LEVELS.items()],
        [InlineKeyboardButton(("✓ " if prefs["language"] == key else "") + label,
                              callback_data=f"set:lang:{key}") for key, label in LANGUAGES.items()],
        [InlineKeyboardButton("✖ Close", callback_data="settings:close")],
    ]
    return InlineKeyboardMarkup(rows)


def result_keyboard(prompt: str) -> InlineKeyboardMarkup:
    # Telegram's native CopyTextButton payload is limited to 256 characters.
    # Use it for short prompts. For longer prompts provide the complete text as
    # a .txt attachment; never send the prompt again as a duplicate chat message.
    telegram_copy_length = len(prompt.encode("utf-16-le")) // 2
    if telegram_copy_length <= 256:
        copy_button = InlineKeyboardButton("📋 Copy Prompt", copy_text=CopyTextButton(text=prompt))
    else:
        copy_button = InlineKeyboardButton("📄 Get Full Prompt", callback_data="prompt:download")
    return InlineKeyboardMarkup([
        [copy_button],
        [InlineKeyboardButton("🌐 Translate", callback_data="translate:open"),
         InlineKeyboardButton("🔄 Regenerate", callback_data="prompt:regenerate")],
        [InlineKeyboardButton("⚙️ Prompt Settings", callback_data="settings:open")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    started = time.perf_counter()
    user = update.effective_user
    if update.message and user:
        username, first_name, last_name = user.username or "", user.first_name or "", user.last_name or ""
        await db_call(get_operations(context).register_user, user.id, username, first_name, last_name)
        schedule_mongo_sync(context, user.id, username, first_name, last_name)
        welcome_text = build_welcome_message(first_name or "there")
        # Telegram file_id avoids uploading the same welcome image on every /start.
        cached_file_id = context.application.bot_data.get("welcome_photo_file_id")
        if cached_file_id:
            await update.message.reply_photo(photo=cached_file_id, caption=welcome_text)
        else:
            with WELCOME_IMAGE.open("rb") as photo:
                sent = await update.message.reply_photo(photo=photo, caption=welcome_text)
            if sent.photo:
                context.application.bot_data["welcome_photo_file_id"] = sent.photo[-1].file_id
        logger.info("/start response user_id=%s elapsed_seconds=%.3f cached_photo=%s",
                    user.id, time.perf_counter() - started, bool(cached_file_id))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "<b>OtakuAura Help</b>\n\n"
            "• Upload a photo or send an image as a file.\n"
            "• Supported formats: JPG, PNG, WebP.\n"
            "• Maximum image size: 10 MB.\n"
            "• Use /settings to choose output format, detail, and language.\n"
            "• Use the result buttons to translate or regenerate your latest prompt.\n"
            "• Use /privacy to manage optional prompt history.\n"
            "• Use /about for privacy and limitations.\n\n"
            "If an upload fails, try sending a smaller image.",
            parse_mode="HTML",
        )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "<b>About OtakuAura</b>\n\n"
            "OtakuAura analyzes an image and writes a text prompt for external image-generation tools. "
            "It does not generate or publish images.\n\n"
            "Images are processed for the request and are not saved permanently by this bot. "
            "For Regenerate, the latest image is temporarily kept in the bot's active session memory. "
            "Prompt history is OFF by default; use /privacy to manage it. The image is sent to the configured AI provider; provider data-handling terms also apply.\n\n"
            "AI descriptions can be imperfect. Please review the prompt before using it.",
            parse_mode="HTML",
        )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return
    prefs = await db_call(get_preferences, context, user.id)
    summary = (
        "<b>⚙️ Prompt Settings</b>\n\n"
        f"Output: <b>{OUTPUT_MODES[prefs['output_mode']]}</b>\n"
        f"Detail: <b>{DETAIL_LEVELS[prefs['detail_level']]}</b>\n"
        f"Language: <b>{LANGUAGES[prefs['language']]}</b>\n\n"
        "Choose your defaults below. Changes are saved for your Telegram account."
    )
    await update.message.reply_text(summary, reply_markup=settings_keyboard(prefs), parse_mode="HTML")


async def show_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    await query.answer()
    prefs = await db_call(get_preferences, context, user.id)
    text = (
        "<b>⚙️ Prompt Settings</b>\n\n"
        f"Output: <b>{OUTPUT_MODES[prefs['output_mode']]}</b>\n"
        f"Detail: <b>{DETAIL_LEVELS[prefs['detail_level']]}</b>\n"
        f"Language: <b>{LANGUAGES[prefs['language']]}</b>\n\n"
        "Choose your defaults below."
    )
    await query.edit_message_text(text, reply_markup=settings_keyboard(prefs), parse_mode="HTML")


async def set_preference_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user or not query.data:
        return
    await query.answer()
    _, kind, value = query.data.split(":", 2)
    change = None
    if kind == "mode" and value in OUTPUT_MODES:
        change = {"output_mode": value}
    elif kind == "detail" and value in DETAIL_LEVELS:
        change = {"detail_level": value}
    elif kind == "lang" and value in LANGUAGES:
        change = {"language": value}
    if not change:
        return
    prefs = await db_call(context.application.bot_data["preferences"].update, user.id, **change)
    text = (
        "<b>⚙️ Prompt Settings</b>\n\n"
        f"Output: <b>{OUTPUT_MODES[prefs['output_mode']]}</b>\n"
        f"Detail: <b>{DETAIL_LEVELS[prefs['detail_level']]}</b>\n"
        f"Language: <b>{LANGUAGES[prefs['language']]}</b>\n\n"
        "<i>Saved successfully ✓</i>"
    )
    await query.edit_message_text(text, reply_markup=settings_keyboard(prefs), parse_mode="HTML")


async def close_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=None)


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return
    enabled = await db_call(get_operations(context).history_enabled, user.id)
    state = "ON" if enabled else "OFF (default)"
    await update.message.reply_text(
        "<b>🔐 Privacy Controls</b>\n\n"
        f"Prompt history: <b>{state}</b>\n"
        "History stores text prompts only — never uploaded images.\n\n"
        "/history_on — opt in to saving your latest 20 prompts\n"
        "/history_off — turn history off and erase saved prompts\n"
        "/history — view saved prompts\n"
        "/clear_history — erase saved prompts now\n\n"
        "History is OFF unless you explicitly enable it.", parse_mode="HTML")


async def history_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return
    await db_call(get_operations(context).set_history, user.id, True)
    await update.message.reply_text("Prompt history enabled. Only future text prompts will be saved; images are never stored.")


async def history_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return
    await db_call(get_operations(context).set_history, user.id, False)
    await update.message.reply_text("Prompt history is now OFF. Any prompts previously saved in your history have been erased.")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return
    store = get_operations(context)
    if not await db_call(store.history_enabled, user.id):
        await update.message.reply_text("Prompt history is OFF. Use /history_on if you want to save future prompts.")
        return
    rows = await db_call(store.get_history, user.id, 10)
    if not rows:
        await update.message.reply_text("Your prompt history is empty.")
        return
    chunks = ["<b>🗂 Your recent prompts</b>"]
    for index, row in enumerate(rows, 1):
        snippet = row["prompt"]
        if len(snippet) > 650:
            snippet = snippet[:647] + "…"
        chunks.append(f"\n{index}. {row['created_at']} · {row['output_mode']}\n{snippet}")
    text = "\n".join(chunks)
    for offset in range(0, len(text), 3800):
        await update.message.reply_text(text[offset:offset + 3800])


async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return
    deleted = await db_call(get_operations(context).clear_history, user.id)
    await update.message.reply_text(f"Deleted {deleted} saved prompt(s) from your history.")


async def user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await update.message.reply_text("This command is available to bot administrators only.")
        return
    store = get_operations(context)
    users = await db_call(store.list_users)
    total = await db_call(store.total_users_count)
    monthly = await db_call(store.monthly_active_users_count)
    if not users:
        await update.message.reply_text("No users registered yet.")
        return
    lines = [f"<b>Registered users: {total:,}</b>",
             f"Monthly active users (last 30 days): <b>{monthly:,}</b>",
             f"Broadcast audience: <b>{total:,}</b>", ""]
    for item in users[:100]:
        display = " ".join(part for part in (item["first_name"], item["last_name"]) if part).strip() or "No name"
        username = f" (@{item['username']})" if item["username"] else ""
        lines.append(f"<code>{item['user_id']}</code> — {display}{username}")
    if len(users) > 100:
        lines.append(f"\nShowing latest 100 of {len(users)} users.")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if not message or not user:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await message.reply_text("This command is available to bot administrators only.")
        return
    announcement = " ".join(context.args).strip()
    if not announcement:
        await message.reply_text("Usage: /broadcast Your announcement message")
        return
    recipients = await db_call(get_operations(context).list_users)
    audience = len(recipients)
    monthly_active = await db_call(get_operations(context).monthly_active_users_count)
    await message.reply_text(f"Broadcast starting for {audience:,} registered users ({monthly_active:,} active in the last 30 days).")
    sent = failed = 0
    for recipient in recipients:
        try:
            await context.bot.send_message(chat_id=recipient["user_id"], text=announcement)
            sent += 1
            await asyncio.sleep(0.05)  # Stay comfortably below Telegram's broadcast rate limit.
        except Exception as exc:
            failed += 1
            logger.info("Broadcast delivery failed for user %s: %s", recipient["user_id"], exc)
    await message.reply_text(f"Broadcast completed.\nSent: {sent}\nFailed: {failed}")


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not update.message or not user:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await update.message.reply_text("This command is available to bot administrators only.")
        return
    stats = await db_call(get_operations(context).admin_stats)
    stats["monthly_active_users"] = await db_call(get_operations(context).monthly_active_users_count)
    stats["registered_users"] = await db_call(get_operations(context).total_users_count)
    await update.message.reply_text(
        "<b>🛠 OtakuAura Operations</b>\n\n"
        f"Requests today: <b>{stats['requests_today']}</b>\n"
        f"Failed requests today: <b>{stats['failures_today']}</b>\n"
        f"Active users today: <b>{stats['active_users_today']}</b>\n"
        f"Monthly active users (30 days): <b>{stats['monthly_active_users']:,}</b>\n"
        f"Total registered users: <b>{stats['registered_users']:,}</b>\n"
        f"Saved prompts: <b>{stats['stored_prompts']}</b>\n\n"
        "Counts reset by the daily reporting window (UTC). No image contents or API keys are shown.", parse_mode="HTML")


async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    await db_call(get_operations(context).register_user, user.id, user.username or "", user.first_name or "", user.last_name or "")
    schedule_mongo_sync(context, user.id, user.username or "", user.first_name or "", user.last_name or "")
    settings = get_settings(context)
    status = await message.reply_text("📥 Image received. Preparing it for analysis…")
    download_started = time.perf_counter()
    telegram_started = download_started
    try:
        if message.photo:
            telegram_file = await message.photo[-1].get_file()
        elif message.document and (message.document.mime_type or "").startswith("image/"):
            telegram_file = await message.document.get_file()
        else:
            await status.edit_text("Please send a JPG, PNG, or WebP image.")
            return
        image_bytes = bytes(await telegram_file.download_as_bytearray())
        telegram_seconds = time.perf_counter() - telegram_started
        prepare_started = time.perf_counter()
        mime_type = await asyncio.to_thread(validate_image, image_bytes, settings.max_image_bytes)
        image_bytes, mime_type = await asyncio.to_thread(
            prepare_image_for_analysis, image_bytes, mime_type, settings.max_analysis_image_dimension
        )
        prepare_seconds = time.perf_counter() - prepare_started
        logger.info("Image ready user_id=%s bytes=%s telegram_download_seconds=%.3f image_prepare_seconds=%.3f",
                    user.id, len(image_bytes), telegram_seconds, prepare_seconds)
    except ValueError as exc:
        await status.edit_text(str(exc))
        return
    except Exception:
        logger.exception("Image download failed")
        await status.edit_text("I couldn't download that image. Please try again.")
        return

    allowed, reason = await check_usage(context, user.id)
    if not allowed:
        await status.edit_text(reason)
        return
    context.user_data["last_image"] = image_bytes
    context.user_data["last_mime_type"] = mime_type
    await generate_for_user(message, context, user.id, image_bytes, mime_type, status_message=status)


async def generate_for_user(message, context, user_id: int, image_bytes: bytes, mime_type: str, status_message=None) -> None:
    prefs = await db_call(get_preferences, context, user_id)
    status = status_message or await message.reply_text("🔎 Analyzing your image and creating a prompt…")
    await status.edit_text("🔎 Analyzing your image and creating a prompt…")
    try:
        await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
        ai_started = time.perf_counter()
        prompt = await run_ai_with_retry(
            context, get_provider(context).create_prompt,
            image_bytes, mime_type, prefs["detail_level"], prefs["output_mode"], prefs["language"],
        )
        ai_seconds = time.perf_counter() - ai_started
        max_chars = get_settings(context).max_prompt_chars
        if len(prompt) > max_chars:
            prompt = prompt[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
        context.user_data["last_base_prompt"] = prompt
        context.user_data["last_prompt"] = prompt
        context.user_data["last_prompt_language"] = prefs["language"]
        await db_call(get_operations(context).save_prompt, user_id, prompt, prefs["output_mode"], prefs["language"])
        await db_call(get_operations(context).increment_counter, "prompts_generated")
        logger.info("Prompt generated user_id=%s ai_seconds=%.3f chars=%s mode=%s", user_id, ai_seconds, len(prompt), prefs["output_mode"])
        await status.edit_text(format_prompt_message(prompt), reply_markup=result_keyboard(prompt))
    except Exception:
        await db_call(get_operations(context).record_event, user_id, "failed")
        await db_call(get_operations(context).increment_counter, "generation_failures")
        logger.exception("Prompt generation failed")
        await status.edit_text("Sorry, I couldn't analyze this image right now. Please try again in a little while.")


async def regenerate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    await query.answer("Regenerating from the same image…")
    image_bytes = context.user_data.get("last_image")
    mime_type = context.user_data.get("last_mime_type")
    if not image_bytes or not mime_type:
        await query.message.reply_text("Please upload the image again to regenerate its prompt.")
        return
    allowed, reason = await check_usage(context, user.id, cooldown_seconds=0)
    if not allowed:
        await query.message.reply_text(reason)
        return
    prefs = await db_call(get_preferences, context, user.id)
    try:
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        ai_started = time.perf_counter()
        prompt = await run_ai_with_retry(
            context, get_provider(context).create_prompt,
            image_bytes, mime_type, prefs["detail_level"], prefs["output_mode"], prefs["language"],
        )
        ai_seconds = time.perf_counter() - ai_started
        max_chars = get_settings(context).max_prompt_chars
        if len(prompt) > max_chars:
            prompt = prompt[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
        context.user_data["last_base_prompt"] = prompt
        context.user_data["last_prompt"] = prompt
        context.user_data["last_prompt_language"] = prefs["language"]
        await db_call(get_operations(context).save_prompt, user.id, prompt, prefs["output_mode"], prefs["language"])
        await db_call(get_operations(context).increment_counter, "prompts_regenerated")
        logger.info("Prompt regenerated user_id=%s ai_seconds=%.3f chars=%s", user.id, ai_seconds, len(prompt))
        await query.message.reply_text(format_prompt_message(prompt), reply_markup=result_keyboard(prompt))
    except Exception:
        await db_call(get_operations(context).record_event, user.id, "failed")
        await db_call(get_operations(context).increment_counter, "generation_failures")
        logger.exception("Prompt regeneration failed")
        await query.message.reply_text("Regeneration failed. Please try again later.")


async def download_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return
    prompt = context.user_data.get("last_prompt")
    if not prompt:
        await query.answer("Generate a prompt first.", show_alert=True)
        return
    await query.answer("Preparing your full prompt file…")
    payload = BytesIO(prompt.encode("utf-8"))
    payload.name = "otakuaura_prompt.txt"
    await query.message.reply_document(
        document=InputFile(payload, filename="otakuaura_prompt.txt"),
        caption=("Your complete prompt is attached as a text file. Open it and use Select all → Copy. "
                 "Telegram's native one-tap Copy Text button supports prompts up to 256 characters."),
    )


async def translate_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    if not context.user_data.get("last_base_prompt"):
        await query.message.reply_text("Generate a prompt first, then you can translate it.")
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"translate:to:{key}")
        for key, label in LANGUAGES.items()
    ]])
    await query.message.reply_text("Choose the language for this prompt:", reply_markup=keyboard)


async def translate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer("Translating prompt…")
    target = query.data.rsplit(":", 1)[-1]
    if target not in LANGUAGES:
        return
    source = context.user_data.get("last_base_prompt")
    if not source:
        await query.message.reply_text("Generate a prompt first, then you can translate it.")
        return
    allowed, reason = await check_usage(context, update.effective_user.id, cooldown_seconds=0)
    if not allowed:
        await query.message.reply_text(reason)
        return
    try:
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
        translated = await run_ai_with_retry(context, get_provider(context).translate_prompt, source, target)
        max_chars = get_settings(context).max_prompt_chars
        if len(translated) > max_chars:
            translated = translated[:max_chars].rsplit(" ", 1)[0].rstrip() + "…"
        context.user_data["last_prompt"] = translated
        prefs = await db_call(get_preferences, context, update.effective_user.id)
        await db_call(get_operations(context).save_prompt, update.effective_user.id, translated, prefs["output_mode"], target)
        await db_call(get_operations(context).increment_counter, "prompts_translated")
        await query.message.reply_text(format_prompt_message(translated), reply_markup=result_keyboard(translated))
    except Exception:
        await db_call(get_operations(context).record_event, update.effective_user.id, "failed")
        await db_call(get_operations(context).increment_counter, "translation_failures")
        logger.exception("Prompt translation failed")
        await query.message.reply_text("Translation failed. Please try again later.")



async def addkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.message
    if not user or not message:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await message.reply_text("You are not authorized to manage API keys.")
        return
    if len(context.args) != 1:
        await message.reply_text("Usage: /addkey YOUR_GEMINI_API_KEY\nSend the key only in a private chat with this bot.")
        return
    key = context.args[0].strip()
    store = context.application.bot_data["gemini_key_store"]
    try:
        added = store.add(key)
        all_keys = tuple(dict.fromkeys(get_settings(context).gemini_api_keys + tuple(store.list_keys())))
        get_provider(context).update_keys(all_keys)
        try:
            await message.delete()
        except Exception:
            pass
        await message.reply_text("Gemini API key added and activated." if added else "This key is already registered.")
    except Exception:
        logger.exception("Could not add Gemini API key")
        await message.reply_text("Could not save/activate the key. Check server storage and logs.")


async def removekey_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.message
    if not user or not message:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await message.reply_text("You are not authorized to manage API keys.")
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await message.reply_text("Usage: /removekey NUMBER (number shown by /listkeys)")
        return
    store = context.application.bot_data["gemini_key_store"]
    removed = store.remove(int(context.args[0]))
    if removed is None:
        await message.reply_text("Invalid key number. Use /listkeys to see removable keys.")
        return
    try:
        get_provider(context).update_keys(tuple(dict.fromkeys(get_settings(context).gemini_api_keys + tuple(store.list_keys()))))
    except ValueError:
        # Never remove the final usable key; restore it before reporting.
        store.add(removed)
        await message.reply_text("Cannot remove the last configured Gemini key.")
        return
    await message.reply_text("Gemini key removed. (Environment-variable keys cannot be removed with this command.)")


async def listkeys_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.message
    if not user or not message:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await message.reply_text("You are not authorized to view API key status.")
        return
    env_count = len(get_settings(context).gemini_api_keys)
    stored = context.application.bot_data["gemini_key_store"].list_keys()
    total = len(tuple(dict.fromkeys(get_settings(context).gemini_api_keys + tuple(stored))))
    lines = ["<b>Gemini API key status</b>", f"Active keys: {total}", f"Environment keys: {env_count}", f"Admin-added keys: {len(stored)}", ""]
    lines.extend(f"{i}. Admin-added key (hidden)" for i, _ in enumerate(stored, 1))
    lines.append("Use /addkey KEY to add and /removekey NUMBER to remove an admin-added key.")
    await message.reply_text("\n".join(lines), parse_mode="HTML")


async def key_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.message
    if not user or not message:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await message.reply_text("You are not authorized to view API key status.")
        return
    count = len(get_provider(context).api_keys)
    await message.reply_text(f"Gemini provider is configured with {count} key(s). Keys are never displayed.")



async def sleep_wake_status_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Block non-admin updates while sleeping, but keep admin controls reachable."""
    operations = context.application.bot_data["operations"]
    settings = context.application.bot_data["settings"]
    if not await db_call(operations.is_sleeping):
        return
    user = update.effective_user
    if user and user.id in settings.admin_user_ids:
        return
    if update.callback_query:
        await update.callback_query.answer("OtakuAura is sleeping. Please try again later.", show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text(
            "😴 OtakuAura is currently in Sleep Mode. Please try again later."
        )
    raise ApplicationHandlerStop


async def sleep_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await message.reply_text("You are not authorized to use this command.")
        return
    operations = get_operations(context)
    if await db_call(operations.is_sleeping):
        await message.reply_text("😴 OtakuAura is already in Sleep Mode. Use /wake to resume.")
        return
    await db_call(operations.set_sleeping, True)
    logger.warning("Sleep Mode enabled by admin user_id=%s", user.id)
    await message.reply_text("😴 OtakuAura is now in Sleep Mode. Admin commands /wake and /status will remain available.")


async def wake_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await message.reply_text("You are not authorized to use this command.")
        return
    operations = get_operations(context)
    await db_call(operations.set_sleeping, False)
    logger.warning("Sleep Mode disabled by admin user_id=%s", user.id)
    await message.reply_text("☀️ OtakuAura is awake and ready to use!")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user, message = update.effective_user, update.effective_message
    if not user or not message:
        return
    if user.id not in get_settings(context).admin_user_ids:
        await message.reply_text("You are not authorized to use this command.")
        return
    sleeping = await db_call(get_operations(context).is_sleeping)
    await message.reply_text("😴 Status: Sleep Mode" if sleeping else "🟢 Status: Active")


def build_application(settings: Settings) -> Application:
    settings.validate()
    key_store = GeminiKeyStore(os.getenv("GEMINI_KEYS_FILE", "data/gemini_keys.json"))
    all_keys = tuple(dict.fromkeys(settings.gemini_api_keys + tuple(key_store.list_keys())))
    provider = GeminiVisionProvider(all_keys or (settings.gemini_api_key,), settings.gemini_model)
    preferences = PreferenceStore(settings.database_path)
    operations = OperationsStore(settings.database_path, settings.mongo_uri,
                                 os.getenv("MONGO_DB_NAME", "otakuaura").strip() or "otakuaura")
    application = (Application.builder().token(settings.telegram_bot_token)
                   .concurrent_updates(12).connection_pool_size(16).pool_timeout(10).build())
    application.bot_data["settings"] = settings
    application.bot_data["provider"] = provider
    application.bot_data["gemini_key_store"] = key_store
    application.bot_data["preferences"] = preferences
    application.bot_data["operations"] = operations
    application.bot_data["ai_semaphore"] = asyncio.Semaphore(settings.ai_concurrency)
    # Group -1 runs before regular handlers. Admin updates pass through so /wake
    # remains reachable; all non-admin messages/callbacks are blocked while asleep.
    application.add_handler(TypeHandler(Update, sleep_wake_status_gate), group=-1)
    application.add_handler(CommandHandler("sleep", sleep_command))
    application.add_handler(CommandHandler("wake", wake_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(CommandHandler("history_on", history_on_command))
    application.add_handler(CommandHandler("history_off", history_off_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("clear_history", clear_history_command))
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(CommandHandler("user", user_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("addkey", addkey_command))
    application.add_handler(CommandHandler("removekey", removekey_command))
    application.add_handler(CommandHandler("listkeys", listkeys_command))
    application.add_handler(CommandHandler("key_status", key_status_command))
    application.add_handler(CallbackQueryHandler(set_preference_callback, pattern=r"^set:"))
    application.add_handler(CallbackQueryHandler(show_settings_callback, pattern=r"^settings:open$"))
    application.add_handler(CallbackQueryHandler(close_settings_callback, pattern=r"^settings:close$"))
    application.add_handler(CallbackQueryHandler(regenerate_callback, pattern=r"^prompt:regenerate$"))
    application.add_handler(CallbackQueryHandler(download_prompt_callback, pattern=r"^prompt:download$"))
    application.add_handler(CallbackQueryHandler(translate_menu_callback, pattern=r"^translate:open$"))
    application.add_handler(CallbackQueryHandler(translate_callback, pattern=r"^translate:to:"))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, process_image))
    return application
