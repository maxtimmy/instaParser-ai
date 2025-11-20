from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ContactSnapshot:
    username: str
    full_name: Optional[str]
    profile_url: Optional[str]
    is_active: bool
    last_message_preview: Optional[str]
    last_message_at_utc: Optional[datetime]
    scraped_at_utc: datetime
    has_unread: bool = False  # 👈 новый флаг «есть непрочитанные»


@dataclass
class MessageSnapshot:
    """
    Снимок одного сообщения в чате Instagram.
    Используется при парсинге истории переписки через Selenium.
    """
    contact_username: str
    sender: str  # 'self' (мы) или 'peer' (собеседник)
    text: str
    timestamp_utc: Optional[datetime]
    scraped_at_utc: datetime