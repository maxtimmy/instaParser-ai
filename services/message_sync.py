# services/message_sync.py

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.models import MessageSnapshot
from db.message_repository import MessageRepository


@dataclass
class MessageSyncResult:
    saved: int


class MessageSyncService:
    """
    Сервис, который принимает список MessageSnapshot и сохраняет их в БД.
    """

    def __init__(self, message_repo: MessageRepository) -> None:
        self._repo = message_repo

    def sync_messages(self, messages: List[MessageSnapshot]) -> MessageSyncResult:
        if not messages:
            return MessageSyncResult(saved=0)
        saved = self._repo.bulk_insert(messages)
        return MessageSyncResult(saved=saved)