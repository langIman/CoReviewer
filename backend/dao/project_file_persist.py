"""上传项目原始文件的持久化层。

`file_store._project_store` 是进程内缓存，重启后丢失。
本模块把同一份 dict 落到 SQLite `project_files` 表，
让后端重启 / 前端刷新后仍能拿到源代码（drawer + QA + 重新生成都依赖它）。
"""

from __future__ import annotations

import logging

from backend.dao.database import get_connection

logger = logging.getLogger(__name__)


def save_project_files(project_name: str, files: dict[str, str]) -> None:
    """整组覆盖写入：先清同 project_name，再批量插入。"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM project_files WHERE project_name = ?", (project_name,))
        if files:
            conn.executemany(
                "INSERT INTO project_files (project_name, path, content) VALUES (?, ?, ?)",
                [(project_name, p, c) for p, c in files.items()],
            )
        conn.commit()
        logger.info("Project files saved: project=%s files=%d", project_name, len(files))
    finally:
        conn.close()


def load_project_files(project_name: str) -> dict[str, str]:
    """按 project_name 读全部文件。无则返回 {}。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT path, content FROM project_files WHERE project_name = ?",
            (project_name,),
        ).fetchall()
        return {row["path"]: row["content"] for row in rows}
    finally:
        conn.close()


def delete_project_files(project_name: str) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM project_files WHERE project_name = ?", (project_name,))
        conn.commit()
    finally:
        conn.close()
