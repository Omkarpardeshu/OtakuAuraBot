from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    gemini_api_key: str
    mongo_uri: str = ""
    gemini_api_keys: tuple[str, ...] = ()
    gemini_model: str = "gemini-3.8-flash"
    webhook_secret: str = ""
    max_image_bytes: int = 10 * 1024 * 1024
    max_analysis_image_dimension: int = 2560
    max_prompt_chars: int = 3900
    database_path: str = "data/otakuaura.sqlite3"
    admin_user_ids: tuple[int, ...] = ()
    user_daily_limit: int = 20
    global_daily_limit: int = 500
    request_cooldown_seconds: int = 3
    ai_max_retries: int = 1
    ai_concurrency: int = 3

    @classmethod
    def from_env(cls) -> "Settings":
        raw_admins = os.getenv("ADMIN_USER_IDS", "")
        admins = tuple(int(item.strip()) for item in raw_admins.split(",") if item.strip().isdigit())
        primary_gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        extra_gemini_keys = tuple(
            key.strip() for key in os.getenv("GEMINI_API_KEYS", "").split(",") if key.strip()
        )
        gemini_keys = tuple(dict.fromkeys(([primary_gemini_key] if primary_gemini_key else []) + list(extra_gemini_keys)))
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            gemini_api_key=primary_gemini_key,
            gemini_api_keys=gemini_keys,
            mongo_uri=os.getenv("MONGO_URI", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip(),
            webhook_secret=os.getenv("WEBHOOK_SECRET", "").strip(),
            max_image_bytes=int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024))),
            max_analysis_image_dimension=max(512, int(os.getenv("MAX_ANALYSIS_IMAGE_DIMENSION", "2560"))),
            max_prompt_chars=int(os.getenv("MAX_PROMPT_CHARS", "3900")),
            database_path=os.getenv("DATABASE_PATH", "data/otakuaura.sqlite3").strip() or "data/otakuaura.sqlite3",
            admin_user_ids=admins,
            user_daily_limit=max(1, int(os.getenv("USER_DAILY_LIMIT", "20"))),
            global_daily_limit=max(0, int(os.getenv("GLOBAL_DAILY_LIMIT", "500"))),
            request_cooldown_seconds=max(0, int(os.getenv("REQUEST_COOLDOWN_SECONDS", "3"))),
            ai_max_retries=max(0, min(5, int(os.getenv("AI_MAX_RETRIES", "1")))),
            ai_concurrency=max(1, min(20, int(os.getenv("AI_CONCURRENCY", "3")))),
        )

    def validate(self, require_webhook: bool = False) -> None:
        missing = []
        if not self.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not (self.gemini_api_keys or self.gemini_api_key):
            missing.append("GEMINI_API_KEY (or GEMINI_API_KEYS)")
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
        if not self.gemini_model:
            raise RuntimeError("GEMINI_MODEL must not be empty.")
        if self.max_image_bytes <= 0:
            raise RuntimeError("MAX_IMAGE_BYTES must be greater than zero.")
        if self.max_analysis_image_dimension < 512:
            raise RuntimeError("MAX_ANALYSIS_IMAGE_DIMENSION must be at least 512.")
        if not 1 <= self.max_prompt_chars <= 3900:
            raise RuntimeError("MAX_PROMPT_CHARS must be between 1 and 3900 for Telegram message safety.")
        if require_webhook and not self.webhook_secret:
            raise RuntimeError("WEBHOOK_SECRET must be set when RENDER_EXTERNAL_URL is configured.")
