"""Wiki 页面 id 约定。

集中管理各类页面 id 的生成与判断，避免字符串拼接散落在各处。
设计原则：
- id 只含 ASCII，便于在 URL 锚点 (#wiki:<id>) 中使用
- 模块/章节/专题 id 用索引（稳定性优于名字 slug，避免中文转义问题）
"""

from __future__ import annotations


OVERVIEW_ID = "overview"

CATEGORY_ARCHITECTURE_ID = "cat_architecture"
CATEGORY_MODULES_ID = "cat_modules"
CATEGORY_TOPICS_ID = "cat_topics"

CATEGORY_IDS = {
    CATEGORY_ARCHITECTURE_ID,
    CATEGORY_MODULES_ID,
    CATEGORY_TOPICS_ID,
}


def module_id(index: int) -> str:
    return f"module_{index}"


def chapter_id(index: int) -> str:
    return f"chapter_{index}"


def topic_id(index: int) -> str:
    return f"topic_{index}"


def is_category_id(page_id: str) -> bool:
    return page_id in CATEGORY_IDS


def is_module_id(page_id: str) -> bool:
    return page_id.startswith("module_")


def is_chapter_id(page_id: str) -> bool:
    return page_id.startswith("chapter_")


def is_topic_id(page_id: str) -> bool:
    return page_id.startswith("topic_")
