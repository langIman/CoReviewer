"""WikiDocument 持久化存储。

对应 WIKI_REFACTOR_PLAN.md 第四节：
- wiki_documents 表：保存项目级元数据（hash、生成时间、index）
- wiki_pages 表：扁平存放所有页面，按 (project_name, page_id) 主键

提供 Wiki 文档 / 单页两种粒度的读写，支持懒加载的 pending → generated 流转。
"""

from __future__ import annotations

import json
import logging

from backend.dao.database import get_connection
from backend.models.wiki_models import (
    PageMetadata,
    WikiDocument,
    WikiIndex,
    WikiPage,
)

logger = logging.getLogger(__name__)


# ---------------------------- 写入 ----------------------------


def save_wiki_document(doc: WikiDocument) -> None:
    """清旧 + 批量写入整份 WikiDocument。"""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM wiki_documents WHERE project_name = ?",
            (doc.project_name,),
        )
        conn.execute(
            "DELETE FROM wiki_pages WHERE project_name = ?",
            (doc.project_name,),
        )

        conn.execute(
            "INSERT INTO wiki_documents (project_name, project_hash, generated_at, index_json) "
            "VALUES (?, ?, ?, ?)",
            (
                doc.project_name,
                doc.project_hash,
                doc.generated_at,
                doc.index.model_dump_json(),
            ),
        )

        for page in doc.pages:
            _insert_page(conn, doc.project_name, page)

        conn.commit()
        logger.info(
            "Wiki saved: project=%s pages=%d", doc.project_name, len(doc.pages)
        )
    finally:
        conn.close()


def upsert_page(project_name: str, page: WikiPage) -> None:
    """写入或覆盖单个页面（用于懒加载 pending → generated）。"""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM wiki_pages WHERE project_name = ? AND page_id = ?",
            (project_name, page.id),
        )
        _insert_page(conn, project_name, page)
        conn.commit()
    finally:
        conn.close()


def clear_project_wiki(project_name: str) -> None:
    """删除指定项目的整份 Wiki。"""
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM wiki_documents WHERE project_name = ?", (project_name,)
        )
        conn.execute(
            "DELETE FROM wiki_pages WHERE project_name = ?", (project_name,)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------- 读取 ----------------------------


def load_wiki_document(project_name: str) -> WikiDocument | None:
    """重建完整 WikiDocument，无数据则返回 None。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT project_hash, generated_at, index_json "
            "FROM wiki_documents WHERE project_name = ?",
            (project_name,),
        ).fetchone()
        if row is None:
            return None

        index = WikiIndex.model_validate_json(row["index_json"]) if row["index_json"] else WikiIndex()

        page_rows = conn.execute(
            "SELECT page_id, type, title, path, status, content_md, metadata_json "
            "FROM wiki_pages WHERE project_name = ?",
            (project_name,),
        ).fetchall()

        pages = [_row_to_page(r) for r in page_rows]

        return WikiDocument(
            project_name=project_name,
            project_hash=row["project_hash"],
            generated_at=row["generated_at"],
            pages=pages,
            index=index,
        )
    finally:
        conn.close()


def load_page(project_name: str, page_id: str) -> WikiPage | None:
    """读取单个页面，不存在返回 None。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT page_id, type, title, path, status, content_md, metadata_json "
            "FROM wiki_pages WHERE project_name = ? AND page_id = ?",
            (project_name, page_id),
        ).fetchone()
        return _row_to_page(row) if row else None
    finally:
        conn.close()


def get_project_hash(project_name: str) -> str | None:
    """用于幂等判断：项目内容未变就不重新生成。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT project_hash FROM wiki_documents WHERE project_name = ?",
            (project_name,),
        ).fetchone()
        return row["project_hash"] if row else None
    finally:
        conn.close()


def has_wiki(project_name: str) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM wiki_documents WHERE project_name = ? LIMIT 1",
            (project_name,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------- 内部工具 ----------------------------


def _insert_page(conn, project_name: str, page: WikiPage) -> None:
    conn.execute(
        "INSERT INTO wiki_pages (page_id, project_name, type, title, path, status, "
        "content_md, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            page.id,
            project_name,
            page.type,
            page.title,
            page.path,
            page.status,
            page.content_md,
            page.metadata.model_dump_json(),
        ),
    )


def _row_to_page(row) -> WikiPage:
    metadata = (
        PageMetadata.model_validate_json(row["metadata_json"])
        if row["metadata_json"]
        else PageMetadata()
    )
    return WikiPage(
        id=row["page_id"],
        type=row["type"],
        title=row["title"],
        path=row["path"],
        status=row["status"],
        content_md=row["content_md"],
        metadata=metadata,
    )
