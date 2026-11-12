"""User-facing message templates for OtakuAura."""

WELCOME_TEMPLATE = """Hello👋.. {username}✨

╔══════════════════════╗
✦ 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 ✦ TO OtakuAura💕
╚══════════════════════╝

♛ 𝐏𝐑𝐎𝐌𝐏𝐓 𝐁𝐎𝐓 ♛

✨ Welcome to the world of creativity.

🎨 Discover premium AI prompts.
🖼️ Explore stunning art styles.
⚡ Create extraordinary AI images.
💎 Unlock your creative potential.

(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)

♛ 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐄𝐗𝐏𝐄𝐑𝐈𝐄𝐍𝐂𝐄
✦ Quality • Creativity • Innovation

(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)

Send me an image or photo, and I’ll turn it into a detailed image-generation prompt.

The prompt is designed for external tools such as Midjourney, Stable Diffusion, and Flux.

How to use 👀: Upload a JPG, PNG, or WebP image 🖼. I’ll analyze it and return a prompt you can copy.

Thank You ❤for using me 🩷💕💕

(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)(⁠◕⁠ᴗ⁠◕⁠✿⁠)"""

PROMPT_HEADER = "✨NEW IMAGE PROCESSING✨\n\n🌺Here is your requested prompt given below 👇\n\n"


def build_welcome_message(first_name: str) -> str:
    """Return the personalized welcome caption, safe for Telegram's 1024-char caption limit."""
    name = (first_name or "there").replace("\n", " ").strip()[:64] or "there"
    message = WELCOME_TEMPLATE.format(username=name)
    if len(message) > 1024:
        raise ValueError("Welcome caption exceeds Telegram's 1024-character limit.")
    return message


def fit_telegram_text(text: str, max_utf16_units: int = 4096) -> str:
    """Trim text to Telegram's message limit, counting UTF-16 code units."""
    if len(text.encode("utf-16-le")) // 2 <= max_utf16_units:
        return text
    suffix = "…"
    budget = max_utf16_units - (len(suffix.encode("utf-16-le")) // 2)
    kept = []
    used = 0
    for character in text:
        units = len(character.encode("utf-16-le")) // 2
        if used + units > budget:
            break
        kept.append(character)
        used += units
    return "".join(kept).rstrip() + suffix


def format_prompt_message(prompt: str) -> str:
    return fit_telegram_text(PROMPT_HEADER + prompt)
