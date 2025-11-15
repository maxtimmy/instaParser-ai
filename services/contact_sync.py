# services/contact_sync.py

from typing import Iterable

from core.models import ContactSnapshot
from db.contact_repository import ContactRepository


class ContactSyncService:
    """
    Сервис, который получает "снимки" контактов из Selenium-клиента
    и синхронизирует их с нашей БД через ContactRepository.
    """

    def __init__(self, contact_repo: ContactRepository) -> None:
        self._repo = contact_repo

    def sync_contacts(self, snapshots: Iterable[ContactSnapshot]) -> None:
        """
        Принимает список ContactSnapshot и сохраняет их в БД.
        Пока логика простая: upsert по username/full_name.
        """
        for snap in snapshots:
            # Предполагаем, что в ContactRepository есть метод upsert_from_snapshot
            self._repo.upsert_from_snapshot(snap)