import logging
import os
from app.bot import build_application
from app.config import Settings
from scripts.preflight import run_preflight


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    for check in run_preflight():
        logging.info("Preflight: %s", check)
    settings = Settings.from_env()
    application = build_application(settings)

    # Render web services use Telegram webhooks. Local development uses polling.
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if render_url:
        token_path = "telegram-webhook"
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "10000")),
            url_path=token_path,
            webhook_url=f"{render_url}/{token_path}",
            secret_token=settings.webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
    else:
        application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
