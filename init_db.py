# init_db.py
from __future__ import annotations

from db.contact_repository import ContactRepository
from db.message_repository import MessageRepository


def main():
    print("[INIT] Initializing database...")

    msg_repo = MessageRepository()
    msg_repo.init_schema()
    print("[INIT] messages table created/verified.")

    contacts_repo = ContactRepository()
    contacts_repo.init_schema()
    print("[INIT] contacts table created/verified.")

    print("[INIT] Done.")


if __name__ == "__main__":
    main()