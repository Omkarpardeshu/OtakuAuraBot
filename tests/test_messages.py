from app.messages import build_welcome_message, fit_telegram_text, format_prompt_message


def test_welcome_message_is_personalized_and_within_telegram_caption_limit():
    message = build_welcome_message("Saurabh")
    assert message.startswith("Hello👋.. Saurabh✨")
    assert "✦ 𝐖𝐄𝐋𝐂𝐎𝐌𝐄 ✦ TO OtakuAura💕" in message
    assert "Midjourney, Stable Diffusion, and Flux" in message
    assert len(message) <= 1024


def test_welcome_name_is_sanitized_to_one_line():
    message = build_welcome_message("Aira\nAdmin")
    assert message.startswith("Hello👋.. Aira Admin✨")


def test_generated_prompt_uses_requested_response_header():
    assert format_prompt_message("precise image prompt") == (
        "✨NEW IMAGE PROCESSING✨\n\n"
        "🌺Here is your requested prompt given below 👇\n\n"
        "precise image prompt"
    )


def test_prompt_message_respects_telegram_utf16_limit():
    message = format_prompt_message("😀" * 3900)
    assert len(message.encode("utf-16-le")) // 2 <= 4096
    assert message.startswith("✨NEW IMAGE PROCESSING✨")


def test_copy_text_is_trimmed_to_telegram_limit():
    message = fit_telegram_text("😀" * 5000)
    assert len(message.encode("utf-16-le")) // 2 <= 4096
