# db/message_repository.py

from __future__ import annotations

from typing import Iterable, List, Optional
from datetime import datetime
import sqlite3

from db.connection import get_connection
from core.models import MessageSnapshot


class MessageRepository:
    """
    Работа с таблицей messages.
    """

    def __init__(self) -> None:
        pass

    def _connect(self) -> sqlite3.Connection:
        return get_connection()

    # ---------- схема ----------

    def init_schema(self) -> None:
        """
        Создаёт таблицу messages, если её ещё нет.
        """
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_username TEXT NOT NULL,
                    sender           TEXT NOT NULL,
                    text             TEXT NOT NULL,
                    timestamp_utc    TEXT NULL,
                    scraped_at_utc   TEXT NOT NULL
                )
                """
            )
            conn.commit()


    def get_last_for_contact(self, contact_username: str) -> Optional[sqlite3.Row]:
        with get_connection() as conn:
            cur = conn.execute(
                """
                SELECT contact_username, sender, text, timestamp_utc
                FROM messages
                WHERE contact_username = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (contact_username,),
            )
            row = cur.fetchone()
            return row

    def bulk_insert(self, messages: Iterable[MessageSnapshot]) -> int:
        """
        Сохраняет пачку сообщений. Возвращает количество вставленных строк.
        """
        msgs: List[MessageSnapshot] = list(messages)
        if not msgs:
            return 0

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO messages (
                    contact_username,
                    sender,
                    text,
                    timestamp_utc,
                    scraped_at_utc
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        m.contact_username,
                        m.sender,
                        m.text,
                        m.timestamp_utc.isoformat() if m.timestamp_utc else None,
                        m.scraped_at_utc.isoformat(),
                    )
                    for m in msgs
                ],
            )
            conn.commit()

        return len(msgs)

    def save_message(self, snapshot: MessageSnapshot) -> None:
        """
        Совместимость для вызовов вида save_message(...).
        Сохраняет одно сообщение.
        """
        self.bulk_insert([snapshot])