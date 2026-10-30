import json
import os
import sqlite3
import time
from typing import Any


class Database:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS vacancies (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT,
                url TEXT,
                score INTEGER NOT NULL DEFAULT 0,
                reason TEXT,
                letter TEXT,
                raw_json TEXT,
                hidden INTEGER NOT NULL DEFAULT 0,
                notified INTEGER NOT NULL DEFAULT 0,
                applied INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS oauth_tokens (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                access_token TEXT,
                refresh_token TEXT,
                expires_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        self.conn.commit()

    def upsert_vacancy(self, item: dict[str, Any], score: int, reason: str, letter: str, raw: dict[str, Any]) -> bool:
        now = int(time.time())
        vacancy_id = str(item["id"])
        existing = self.conn.execute("SELECT id FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone()
        if existing:
            self.conn.execute(
                """
                UPDATE vacancies
                SET title = ?, company = ?, url = ?, score = ?, reason = ?, letter = ?, raw_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    item.get("name", ""),
                    (item.get("employer") or {}).get("name", ""),
                    item.get("alternate_url", ""),
                    score,
                    reason,
                    letter,
                    json.dumps(raw, ensure_ascii=False),
                    now,
                    vacancy_id,
                ),
            )
            self.conn.commit()
            return False

        self.conn.execute(
            """
            INSERT INTO vacancies(id, title, company, url, score, reason, letter, raw_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vacancy_id,
                item.get("name", ""),
                (item.get("employer") or {}).get("name", ""),
                item.get("alternate_url", ""),
                score,
                reason,
                letter,
                json.dumps(raw, ensure_ascii=False),
                now,
                now,
            ),
        )
        self.conn.commit()
        return True

    def get_vacancy(self, vacancy_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM vacancies WHERE id = ?", (str(vacancy_id),)).fetchone()

    def mark_notified(self, vacancy_id: str) -> None:
        self.conn.execute("UPDATE vacancies SET notified = 1 WHERE id = ?", (str(vacancy_id),))
        self.conn.commit()

    def hide_vacancy(self, vacancy_id: str) -> None:
        self.conn.execute("UPDATE vacancies SET hidden = 1 WHERE id = ?", (str(vacancy_id),))
        self.conn.commit()

    def mark_applied(self, vacancy_id: str) -> None:
        self.conn.execute("UPDATE vacancies SET applied = 1 WHERE id = ?", (str(vacancy_id),))
        self.conn.commit()

    def unseen_good_vacancies(self, min_score: int, limit: int = 30) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT * FROM vacancies
            WHERE notified = 0 AND hidden = 0 AND applied = 0 AND score >= ?
            ORDER BY score DESC, created_at DESC
            LIMIT ?
            """,
            (min_score, limit),
        ).fetchall()
        return list(rows)

    def set_token(self, access_token: str, refresh_token: str, expires_at: int) -> None:
        self.conn.execute(
            """
            INSERT INTO oauth_tokens(id, access_token, refresh_token, expires_at)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at = excluded.expires_at
            """,
            (access_token, refresh_token, expires_at),
        )
        self.conn.commit()

    def get_token(self) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM oauth_tokens WHERE id = 1").fetchone()

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default
