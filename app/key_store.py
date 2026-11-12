"""Persistent storage for Gemini keys added by an authorized bot admin."""
import json
import os
from pathlib import Path
import threading


class GeminiKeyStore:
    def __init__(self, path: str = "data/gemini_keys.json") -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def list_keys(self) -> list[str]:
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                keys = data.get("keys", []) if isinstance(data, dict) else []
                return list(dict.fromkeys(k.strip() for k in keys if isinstance(k, str) and k.strip()))
            except FileNotFoundError:
                return []
            except (json.JSONDecodeError, OSError):
                return []

    def add(self, key: str) -> bool:
        key = key.strip()
        if not key:
            raise ValueError("API key cannot be empty")
        with self._lock:
            keys = self.list_keys_unlocked()
            if key in keys:
                return False
            keys.append(key)
            self._write(keys)
            return True

    def remove(self, index: int) -> str | None:
        with self._lock:
            keys = self.list_keys_unlocked()
            if index < 1 or index > len(keys):
                return None
            removed = keys.pop(index - 1)
            self._write(keys)
            return removed

    def list_keys_unlocked(self) -> list[str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            keys = data.get("keys", []) if isinstance(data, dict) else []
            return list(dict.fromkeys(k.strip() for k in keys if isinstance(k, str) and k.strip()))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _write(self, keys: list[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps({"keys": keys}, indent=2), encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        temp.replace(self.path)
