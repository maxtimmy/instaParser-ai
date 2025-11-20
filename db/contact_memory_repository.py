from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from db.connection import get_connection


@dataclass
class ContactMemory:
    contact_username: str
    summary: Optional[str]
    json_data: Optional[str]
    updated_at_utc: Optional[str]


class ContactMemoryRepository:
    """
    Репозиторий для работы с таблицей contact_memory.

    Таблица хранит сжатый профиль/«память» по каждому контакту:
      - contact_username — ключ (username в Instagram);
      - summary — краткое текстовое описание;
      - json_data — опциональный JSON с более структурированным профилем;
      - updated_at_utc — ISO-строка с временем последнего обновления (UTC).
    """

    def init_schema(self) -> None:
        """
        Создаёт таблицу contact_memory, если её ещё нет.
        """
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contact_memory (
                    contact_username TEXT PRIMARY KEY,
                    summary TEXT,
                    json_data TEXT,
                    updated_at_utc TEXT
                );
                """
            )
            conn.commit()

    def get_by_username(self, username: str) -> Optional[ContactMemory]:
        """
        Возвращает запись памяти по username или None, если её ещё нет.
        """
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT contact_username, summary, json_data, updated_at_utc
                FROM contact_memory
                WHERE contact_username = ?
                """,
                (username,),
            ).fetchone()

            if row is None:
                return None

            return ContactMemory(
                contact_username=row["contact_username"],
                summary=row["summary"],
                json_data=row["json_data"],
                updated_at_utc=row["updated_at_utc"],
            )

    def upsert(
        self,
        username: str,
        summary: Optional[str],
        json_data: Optional[str],
        updated_at_utc: str,
    ) -> None:
        """
        Создаёт или обновляет запись памяти для контакта.

        ON CONFLICT по contact_username позволяет одним запросом
        и вставлять, и обновлять данные.
        """
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO contact_memory (contact_username, summary, json_data, updated_at_utc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(contact_username) DO UPDATE SET
                    summary = excluded.summary,
                    json_data = excluded.json_data,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (username, summary, json_data, updated_at_utc),
            )
            conn.commit()
