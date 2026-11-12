"""Deployment preflight checks; safe to run before starting the bot."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.config import Settings


def run_preflight() -> list[str]:
    settings = Settings.from_env()
    settings.validate(require_webhook=bool(os.getenv("RENDER_EXTERNAL_URL", "").strip()))
    db_path = Path(settings.database_path).expanduser()
    parent = db_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Verify that the configured database directory is writable without touching
    # an existing database or leaving a probe file behind.
    with tempfile.NamedTemporaryFile(prefix=".otakuaura-write-test-", dir=parent, delete=True):
        pass
    return [
        "Required environment variables are present.",
        f"Database directory is writable: {parent}",
        "Render webhook configuration is valid for this environment.",
    ]


if __name__ == "__main__":
    for item in run_preflight():
        print(f"[OK] {item}")
