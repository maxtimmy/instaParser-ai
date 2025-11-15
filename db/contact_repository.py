from __future__ import annotations

from datetime import datetime
from typing import Iterator, Optional

from db.connection import get_connection
from core.models import ContactSnapshot


class ContactRepository:
    """
    Репозиторий для работы с таблицей contacts.
    Схема:

        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        display_name TEXT,
        profile_url TEXT,
        is_active INTEGER DEFAULT 1,
        last_message_preview TEXT,
        last_message_at_utc TEXT,
        scraped_at_utc TEXT
    """

    def __init__(self) -> None:
        pass

    def _connect(self):
        return get_connection()

    # -------------------------
    #       SCHEMA INIT
    # -------------------------
    def init_schema(self) -> None:
        """
        Создаёт таблицу contacts.
        """
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    display_name TEXT,
                    profile_url TEXT,
                    is_active INTEGER DEFAULT 1,
                    last_message_preview TEXT,
                    last_message_at_utc TEXT,
                    scraped_at_utc TEXT
                );
                """
            )

    # -------------------------
    #        UPSERT
    # -------------------------
    def upsert_from_snapshot(self, snapshot: ContactSnapshot) -> None:
        """
        Вставляет или обновляет запись по username.
        """
        if not snapshot.username:
            return

        username = snapshot.username
        display_name = snapshot.full_name  # сохраняем в display_name!!!
        profile_url = snapshot.profile_url
        is_active = 1 if snapshot.is_active else 0
        last_message_preview = snapshot.last_message_preview

        last_message_at_utc = (
            snapshot.last_message_at_utc.isoformat()
            if snapshot.last_message_at_utc
            else None
        )

        scraped_at_utc = snapshot.scraped_at_utc.isoformat()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO contacts (
                    username,
                    display_name,
                    profile_url,
                    is_active,
                    last_message_preview,
                    last_message_at_utc,
                    scraped_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    display_name = excluded.display_name,
                    profile_url = excluded.profile_url,
                    is_active = excluded.is_active,
                    last_message_preview = excluded.last_message_preview,
                    last_message_at_utc = excluded.last_message_at_utc,
                    scraped_at_utc = excluded.scraped_at_utc
                """,
                (
                    username,
                    display_name,
                    profile_url,
                    is_active,
                    last_message_preview,
                    last_message_at_utc,
                    scraped_at_utc,
                ),
            )
            conn.commit()

    def bulk_upsert(self, snapshots: list[ContactSnapshot]) -> int:
        """
        Массовый upsert контактов из списка с использованием существующей логики upsert_from_snapshot.

        Для каждого snapshot:
        - если username пустой — пропускаем;
        - иначе вызываем upsert_from_snapshot.

        Возвращает количество успешно обработанных snapshot'ов.
        """
        if not snapshots:
            return 0

        processed = 0
        for s in snapshots:
            if not s or not s.username:
                continue
            # используем единый метод, чтобы не дублировать SQL/маппинг полей
            self.upsert_from_snapshot(s)
            processed += 1

        return processed

    # -------------------------
    #       LIST ALL
    # -------------------------
    def list_all(self):
        """
        Возвращает все контакты в виде списка ContactSnapshot.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT 
                    username,
                    display_name,
                    profile_url,
                    is_active,
                    last_message_preview,
                    last_message_at_utc,
                    scraped_at_utc
                FROM contacts
                """
            ).fetchall()

        results = []
        for r in rows:
            results.append(
                ContactSnapshot(
                    username=r[0],
                    full_name=r[1],  # ДА – читаем display_name как full_name
                    profile_url=r[2],
                    is_active=bool(r[3]),
                    last_message_preview=r[4],
                    last_message_at_utc=r[5],
                    scraped_at_utc=r[6],
                )
            )
        return results