from __future__ import annotations

import json
import threading
import sqlite3
from pathlib import Path
from typing import Any


class Database:
    def __init__(self):
        self.path = Path.home() / ".mangakoro" / "mangakoro.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.RLock()
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS favorites (manga_id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history (chapter_id TEXT PRIMARY KEY, manga_id TEXT, data TEXT NOT NULL, read_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.connection.commit()

    def setting(self, key: str, default: Any = None) -> Any:
        with self.lock:
            row = self.connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key: str, value: Any):
        with self.lock:
            self.connection.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
            self.connection.commit()

    def is_favorite(self, manga_id: str) -> bool:
        with self.lock:
            return self.connection.execute("SELECT 1 FROM favorites WHERE manga_id=?", (manga_id,)).fetchone() is not None

    def toggle_favorite(self, manga: dict[str, Any]) -> bool:
        with self.lock:
            if self.is_favorite(manga["id"]):
                self.connection.execute("DELETE FROM favorites WHERE manga_id=?", (manga["id"],))
                value = False
            else:
                self.connection.execute("INSERT OR REPLACE INTO favorites VALUES (?, ?)", (manga["id"], json.dumps(manga)))
                value = True
            self.connection.commit()
            return value

    def favorites(self) -> list[dict[str, Any]]:
        with self.lock:
            return [json.loads(row[0]) for row in self.connection.execute("SELECT data FROM favorites ORDER BY rowid DESC")]

    def add_history(self, chapter: dict[str, Any], manga: dict[str, Any]):
        payload = {"chapter": chapter, "manga": manga}
        with self.lock:
            self.connection.execute("INSERT OR REPLACE INTO history(chapter_id,manga_id,data,read_at) VALUES(?,?,?,CURRENT_TIMESTAMP)", (chapter["id"], manga["id"], json.dumps(payload)))
            self.connection.commit()

    def history(self) -> list[dict[str, Any]]:
        with self.lock:
            return [json.loads(row[0]) for row in self.connection.execute("SELECT data FROM history ORDER BY read_at DESC LIMIT 50")]