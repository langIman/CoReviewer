import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "summaries.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            path TEXT NOT NULL,
            type TEXT NOT NULL,
            summary TEXT NOT NULL,
            project_name TEXT NOT NULL,
            PRIMARY KEY (path, project_name)
        )
    """)
    conn.commit()
    conn.close()
    logger.info("SQLite database initialized at %s", DB_PATH)
