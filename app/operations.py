"""Phase 3 persistence, privacy, usage limits and operational counters."""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from pymongo import MongoClient, DESCENDING
except ImportError:  # MongoDB is optional when MONGO_URI is not configured.
    MongoClient = None
    DESCENDING = -1


class OperationsStore:
    def __init__(self, database_path: str, mongo_uri: str = "", mongo_db_name: str = "otakuaura") -> None:
        self.database_path = database_path
        self.mongo_client = None
        self.mongo_users = None
        if mongo_uri:
            if MongoClient is None:
                raise RuntimeError("MONGO_URI is set but pymongo is not installed.")
            # Fail fast on a bad configured URI rather than silently losing the Mongo user directory.
            self.mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000,
                                            connectTimeoutMS=5000, socketTimeoutMS=5000)
            self.mongo_client.admin.command("ping")
            self.mongo_users = self.mongo_client[mongo_db_name]["bot_users"]
            self.mongo_users.create_index([("user_id", 1)], unique=True)
            self.mongo_users.create_index([("last_seen", DESCENDING)])
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS bot_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL DEFAULT '',
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS user_privacy (
                user_id INTEGER PRIMARY KEY,
                history_enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS prompt_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                output_mode TEXT NOT NULL,
                language TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_history_user_created ON prompt_history(user_id, id DESC)")
            db.execute("""CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                created_epoch INTEGER NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_usage_epoch ON usage_events(created_epoch)")
            # Retain only a bounded operational window; no long-term user activity log.
            db.execute("DELETE FROM usage_events WHERE created_epoch < ?", (int(time.time()) - 60 * 86400,))
            db.execute("""CREATE TABLE IF NOT EXISTS operational_counters (
                name TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS bot_settings (
                name TEXT PRIMARY KEY, value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def history_enabled(self, user_id: int) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT history_enabled FROM user_privacy WHERE user_id=?", (user_id,)).fetchone()
        return bool(row[0]) if row else False

    def set_history(self, user_id: int, enabled: bool) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO user_privacy(user_id,history_enabled) VALUES(?,?) "
                       "ON CONFLICT(user_id) DO UPDATE SET history_enabled=excluded.history_enabled, "
                       "updated_at=CURRENT_TIMESTAMP", (user_id, int(enabled)))
            if not enabled:
                db.execute("DELETE FROM prompt_history WHERE user_id=?", (user_id,))

    def save_prompt(self, user_id: int, prompt: str, output_mode: str, language: str) -> None:
        # Check opt-in and insert in one write transaction so /history_off cannot
        # race with a prompt save and leave a new row behind after deletion.
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT history_enabled FROM user_privacy WHERE user_id=?", (user_id,)).fetchone()
            if not row or not bool(row[0]):
                db.rollback()
                return
            db.execute("INSERT INTO prompt_history(user_id,prompt,output_mode,language) VALUES(?,?,?,?)",
                       (user_id, prompt[:12000], output_mode[:32], language[:32]))
            db.execute("DELETE FROM prompt_history WHERE user_id=? AND id NOT IN "
                       "(SELECT id FROM prompt_history WHERE user_id=? ORDER BY id DESC LIMIT 20)",
                       (user_id, user_id))
            db.commit()

    def get_history(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT id,prompt,output_mode,language,created_at FROM prompt_history "
                               "WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, min(max(limit, 1), 20))).fetchall()
        return [dict(row) for row in rows]

    def clear_history(self, user_id: int) -> int:
        with self._connect() as db:
            cur = db.execute("DELETE FROM prompt_history WHERE user_id=?", (user_id,))
            return cur.rowcount

    def allow_request(self, user_id: int, *, cooldown_seconds: int, user_daily_limit: int,
                      global_daily_limit: int) -> tuple[bool, str]:
        now = int(time.time())
        day_start = now - (now % 86400)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            last = db.execute("SELECT MAX(created_epoch) FROM usage_events WHERE user_id=? AND event='accepted'",
                              (user_id,)).fetchone()[0]
            if last is not None and now - int(last) < cooldown_seconds:
                db.rollback()
                return False, f"Please wait {cooldown_seconds - (now - int(last))} seconds before your next image."
            user_count = db.execute("SELECT COUNT(*) FROM usage_events WHERE user_id=? AND event='accepted' AND created_epoch>=?",
                                    (user_id, day_start)).fetchone()[0]
            if user_count >= user_daily_limit:
                db.rollback()
                return False, f"You've reached today's limit of {user_daily_limit} image requests. Please try again tomorrow."
            total_count = db.execute("SELECT COUNT(*) FROM usage_events WHERE event='accepted' AND created_epoch>=?",
                                     (day_start,)).fetchone()[0]
            if global_daily_limit > 0 and total_count >= global_daily_limit:
                db.rollback()
                return False, "OtakuAura has reached its daily processing capacity. Please try again tomorrow."
            db.execute("INSERT INTO usage_events(user_id,event,created_epoch) VALUES(?,'accepted',?)", (user_id, now))
            db.commit()
        return True, ""

    def record_event(self, user_id: int, event: str) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO usage_events(user_id,event,created_epoch) VALUES(?,?,?)",
                       (user_id, event[:32], int(time.time())))

    def increment_counter(self, name: str) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO operational_counters(name,value) VALUES(?,1) "
                       "ON CONFLICT(name) DO UPDATE SET value=value+1,updated_at=CURRENT_TIMESTAMP", (name,))

    def admin_stats(self) -> dict[str, int]:
        day_start = int(time.time()) - (int(time.time()) % 86400)
        with self._connect() as db:
            accepted = db.execute("SELECT COUNT(*) FROM usage_events WHERE event='accepted' AND created_epoch>=?", (day_start,)).fetchone()[0]
            failed = db.execute("SELECT COUNT(*) FROM usage_events WHERE event='failed' AND created_epoch>=?", (day_start,)).fetchone()[0]
            users = db.execute("SELECT COUNT(DISTINCT user_id) FROM usage_events WHERE created_epoch>=?", (day_start,)).fetchone()[0]
            history = db.execute("SELECT COUNT(*) FROM prompt_history").fetchone()[0]
        return {"requests_today": int(accepted), "failures_today": int(failed),
                "active_users_today": int(users), "stored_prompts": int(history)}

    def register_user(self, user_id: int, username: str = "", first_name: str = "", last_name: str = "") -> None:
        """Persist minimal Telegram identity data locally without remote network calls."""
        with self._connect() as db:
            db.execute("""INSERT INTO bot_users(user_id, username, first_name, last_name)
                VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username, first_name=excluded.first_name,
                last_name=excluded.last_name, last_seen=CURRENT_TIMESTAMP""",
                (user_id, username[:64], first_name[:128], last_name[:128]))

    def sync_mongo_user(self, user_id: int, username: str = "", first_name: str = "", last_name: str = "") -> None:
        """Best-effort remote directory sync; callers should run this off the event loop."""
        if self.mongo_users is None:
            return
        now = datetime.now(timezone.utc)
        self.mongo_users.update_one(
            {"user_id": int(user_id)},
            {"$set": {"username": username[:64], "first_name": first_name[:128],
                      "last_name": last_name[:128], "last_seen": now},
             "$setOnInsert": {"first_seen": now}},
            upsert=True,
        )

    def list_users(self, limit: int = 5000) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 10000)
        if self.mongo_users is not None:
            rows = self.mongo_users.find({}, {"_id": 0}).sort("last_seen", DESCENDING).limit(safe_limit)
            return [dict(row) for row in rows]
        with self._connect() as db:
            rows = db.execute("SELECT user_id, username, first_name, last_name, first_seen, last_seen "
                              "FROM bot_users ORDER BY last_seen DESC LIMIT ?", (safe_limit,)).fetchall()
        return [dict(row) for row in rows]

    def total_users_count(self) -> int:
        if self.mongo_users is not None:
            return int(self.mongo_users.count_documents({}))
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0])

    def monthly_active_users_count(self) -> int:
        """Distinct registered users seen in the rolling last 30 days (not Telegram's official metric)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        if self.mongo_users is not None:
            return int(self.mongo_users.count_documents({"last_seen": {"$gte": cutoff}}))
        cutoff_text = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM bot_users WHERE last_seen >= ?", (cutoff_text,)).fetchone()[0])

    def is_sleeping(self) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT value FROM bot_settings WHERE name='sleep_mode'").fetchone()
        return bool(row and row[0] == "1")

    def set_sleeping(self, sleeping: bool) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO bot_settings(name,value) VALUES('sleep_mode',?) "
                       "ON CONFLICT(name) DO UPDATE SET value=excluded.value, "
                       "updated_at=CURRENT_TIMESTAMP", ("1" if sleeping else "0",))
