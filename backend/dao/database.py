import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "summaries.db")

# Wiki schema 版本。每次结构不兼容变更时 bump 一下，启动时会一次性清空旧 Wiki。
WIKI_SCHEMA_VERSION = 2


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
            resolution_method TEXT,
            project_name TEXT NOT NULL
        )
    """)
    # 兼容老库：resolution_method 列后加，PRAGMA 检测后 ALTER TABLE 添加
    cols = {row[1] for row in conn.execute("PRAGMA table_info(call_edges)")}
    if "resolution_method" not in cols:
        conn.execute("ALTER TABLE call_edges ADD COLUMN resolution_method TEXT")
        logger.info("call_edges schema migrated: +resolution_method")
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wiki_documents (
            project_name TEXT PRIMARY KEY,
            project_hash TEXT,
            generated_at TEXT,
            index_json TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wiki_pages (
            page_id TEXT NOT NULL,
            project_name TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            path TEXT,
            status TEXT NOT NULL,
            content_md TEXT,
            metadata_json TEXT,
            PRIMARY KEY (project_name, page_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_files (
            project_name TEXT NOT NULL,
            path TEXT NOT NULL,
            content TEXT NOT NULL,
            PRIMARY KEY (project_name, path)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qa_conversations (
            id           TEXT PRIMARY KEY,
            project_name TEXT NOT NULL,
            title        TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_qa_conv_project
            ON qa_conversations(project_name, updated_at DESC)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qa_messages (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id  TEXT NOT NULL,
            role             TEXT NOT NULL,
            content          TEXT NOT NULL,
            mode             TEXT,
            tool_events_json TEXT,
            code_refs_json   TEXT,
            created_at       TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES qa_conversations(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_qa_msg_conv
            ON qa_messages(conversation_id, id)
    """)

    # Wiki 结构变更的一次性清理：user_version 落后就清空 wiki_* 表
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current < WIKI_SCHEMA_VERSION:
        conn.execute("DELETE FROM wiki_documents")
        conn.execute("DELETE FROM wiki_pages")
        conn.execute(f"PRAGMA user_version = {WIKI_SCHEMA_VERSION}")
        logger.info(
            "Wiki schema bumped %d -> %d, cleared wiki_documents/wiki_pages",
            current, WIKI_SCHEMA_VERSION,
        )

    conn.commit()
    conn.close()
    logger.info("SQLite database initialized at %s", DB_PATH)
