from db.contact_repository import ContactRepository
from db.message_repository import MessageRepository
from db.contact_memory_repository import ContactMemoryRepository


def init_db() -> None:
    contact_repo = ContactRepository()
    message_repo = MessageRepository()
    memory_repo = ContactMemoryRepository()

    contact_repo.init_schema()
    message_repo.init_schema()
    memory_repo.init_schema()


if __name__ == "__main__":
    init_db()