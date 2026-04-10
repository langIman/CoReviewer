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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            qualified_name TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            file TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            decorators TEXT DEFAULT '[]',
            docstring TEXT,
            params TEXT DEFAULT '[]',
            is_entry INTEGER DEFAULT 0,
            project_name TEXT NOT NULL,
            PRIMARY KEY (qualified_name, project_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS call_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caller TEXT NOT NULL,
            callee_name TEXT NOT NULL,
            callee_resolved TEXT,
            file TEXT DEFAULT '',
            line INTEGER DEFAULT 0,
            call_type TEXT DEFAULT 'direct',
            project_name TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS modules (
            path TEXT NOT NULL,
            line_count INTEGER DEFAULT 0,
            symbol_count INTEGER DEFAULT 0,
            imports TEXT DEFAULT '[]',
            project_name TEXT NOT NULL,
            PRIMARY KEY (path, project_name)
        )
    """)
    conn.commit()
    conn.close()
    logger.info("SQLite database initialized at %s", DB_PATH)
