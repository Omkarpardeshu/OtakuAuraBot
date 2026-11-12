"""Persistent, minimal per-user prompt preferences (SQLite)."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_PREFERENCES: dict[str, str] = {
    "output_mode": "tags",
    "detail_level": "standard",
    "language": "English",
}


class PreferenceStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    output_mode TEXT NOT NULL DEFAULT 'tags',
                    detail_level TEXT NOT NULL DEFAULT 'standard',
                    language TEXT NOT NULL DEFAULT 'English',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            # Product direction is now anime-tag-first. Migrate prior untouched/default
            # natural mode users to tags; users can still select Natural in /settings.
            connection.execute(
                "UPDATE user_preferences SET output_mode = 'tags', updated_at = CURRENT_TIMESTAMP WHERE output_mode = 'natural'"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def get(self, user_id: int) -> dict[str, str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT output_mode, detail_level, language FROM user_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return DEFAULT_PREFERENCES.copy()
        return {key: str(row[key]) for key in DEFAULT_PREFERENCES}

    def update(self, user_id: int, **changes: Any) -> dict[str, str]:
        current = self.get(user_id)
        allowed = set(DEFAULT_PREFERENCES)
        for key, value in changes.items():
            if key in allowed and isinstance(value, str):
                current[key] = value
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO user_preferences (user_id, output_mode, detail_level, language)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     output_mode=excluded.output_mode,
                     detail_level=excluded.detail_level,
                     language=excluded.language,
                     updated_at=CURRENT_TIMESTAMP""",
                (user_id, current["output_mode"], current["detail_level"], current["language"]),
            )
        return current
