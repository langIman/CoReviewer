"""Wiki 数据模型。

用于 Wiki 文档结构、页面内容、元数据和导航索引。API 层直接使用这些模型序列化。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PageType = Literal["overview", "category", "chapter", "topic", "module"]
PageStatus = Literal["generated"]


class CodeRef(BaseModel):
    """Markdown 里 [text](#code:ref_id) 指向的代码位置。"""

    file: str
    start_line: int
    end_line: int
    symbol: str | None = None


class ModuleInfo(BaseModel):
    """type='module' 页面独有的元数据。"""

    files: list[str] = Field(default_factory=list)  # 文件路径字符串列表


class PageMetadata(BaseModel):
    """页面元数据：导航链接 + 代码引用 + 类型特有字段。"""

    outgoing_links: list[str] = Field(default_factory=list)
    code_refs: dict[str, CodeRef] = Field(default_factory=dict)
    module_info: ModuleInfo | None = None
    brief: str | None = None   # chapter/topic 的写作说明（由 outliner 产生）


class WikiPage(BaseModel):
    """Wiki 页面结构（overview/category/chapter/topic/module 共用）。"""

    id: str                    # "overview" | "cat_xxx" | "chapter_N" | "topic_N" | "module_N"
    type: PageType
    title: str
    path: str | None = None    # module 类型对应的实际路径（本项目中实为 None，保留字段）
    status: PageStatus = "generated"
    content_md: str | None = None   # category 类型为 None
    metadata: PageMetadata = Field(default_factory=PageMetadata)


class WikiIndexNode(BaseModel):
    """索引树上的一个节点：仅保存标题和子节点 id 列表。"""

    title: str
    children: list[str] = Field(default_factory=list)


class WikiIndex(BaseModel):
    """前端导航树：以 overview 为根的页面层级。"""

    root: str = "overview"
    tree: dict[str, WikiIndexNode] = Field(default_factory=dict)


class WikiDocument(BaseModel):
    """一个项目完整的 Wiki 文档。"""

    project_name: str
    project_hash: str          # 基于文件内容 hash，幂等判断
    generated_at: str          # ISO8601 字符串
    pages: list[WikiPage] = Field(default_factory=list)
    index: WikiIndex = Field(default_factory=WikiIndex)
