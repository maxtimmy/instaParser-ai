# db/connection.py
import os
import sqlite3
from pathlib import Path
from typing import Iterator, ContextManager
from contextlib import contextmanager

DB_PATH_ENV = "MYGRAM_DB_PATH"
DEFAULT_DB_FILE = "mygram.db"


def get_db_path() -> str:
    """
    Возвращает путь к файлу БД.
    Можно переопределить через переменную окружения MYGRAM_DB_PATH.
    """
    env_path = os.getenv(DB_PATH_ENV)
    if env_path:
        return env_path

    base_dir = Path(__file__).resolve().parents[1]
    return str(base_dir / DEFAULT_DB_FILE)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()