from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from datetime import datetime, UTC

from db.contact_repository import ContactRepository
from db.message_repository import MessageRepository
from db.contact_memory_repository import ContactMemoryRepository, ContactMemory


@dataclass
class ContactState:
    username: str
    memory_summary: Optional[str]
    memory_json: Optional[Dict[str, Any]]
    last_messages: List[Any]


class ContactStateService:
    """
    Сервис, объединяющий контакты, историю сообщений и память контактов.
    Работает как единая точка для получения состояния контакта и обновления данных.
    """

    def __init__(
        self,
        contact_repo: ContactRepository,
        message_repo: MessageRepository,
        memory_repo: ContactMemoryRepository,
        history_limit: int = 20,
    ):
        self.contact_repo = contact_repo
        self.message_repo = message_repo
        self.memory_repo = memory_repo
        self.history_limit = history_limit

    def get_contact_state(self, username: str) -> ContactState:
        """
        Возвращает состояние контакта:
        - гарантирует наличие контакта в таблице contacts,
        - достаёт summary/JSON память,
        - достаёт последние N сообщений.
        """
        # ensure contact exists
        self.contact_repo.ensure_exists(username)

        # load memory (may be None)
        memory: Optional[ContactMemory] = self.memory_repo.get_by_username(username)

        summary = memory.summary if memory else None
        json_data = memory.json_data if memory else None

        # last messages
        last_messages = self.message_repo.get_last_messages(username, self.history_limit)

        return ContactState(
            username=username,
            memory_summary=summary,
            memory_json=json_data,
            last_messages=last_messages,
        )

    def save_message(self, username: str, direction: str, text: str) -> None:
        """
        Сохраняет входящее или исходящее сообщение.
        """
        created_at = datetime.now(UTC).isoformat()
        self.message_repo.insert(username, direction, text, created_at)

    def update_contact_memory(
        self,
        username: str,
        summary: Optional[str],
        json_data: Optional[str],
    ) -> None:
        """
        Обновляет память контакта (summary + JSON).
        """
        updated_at = datetime.now(UTC).isoformat()
        self.memory_repo.upsert(username, summary, json_data, updated_at)
