# core/models.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ContactSnapshot:
    """
    "Снимок" одной карточки контакта из Direct.
    """
    username: Optional[str]
    full_name: Optional[str]
    profile_url: Optional[str]
    is_active: bool

    last_message_preview: Optional[str]
    last_message_at_utc: Optional[datetime]
    scraped_at_utc: datetime


@dataclass
class MessageSnapshot:
    """
    "Снимок" одного сообщения в чате.
    """
    contact_username: str          # с кем чат
    sender: str                    # 'me', 'contact' или 'unknown'
    text: str
    timestamp_utc: Optional[datetime]
    scraped_at_utc: datetime