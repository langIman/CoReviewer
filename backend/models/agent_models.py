"""Multi-Agent 系统数据实体。"""

from dataclasses import dataclass, field


@dataclass
class FunctionSummary:
    """Worker 对一个函数的语义摘要。"""

    qualified_name: str  # "services/auth_service.py::AuthService.register"
    file: str
    line_start: int
    line_end: int
    summary: str  # LLM 生成的 1-2 句中文描述
    calls: list[str] = field(default_factory=list)  # 被调函数 qualified_names
    params: list[str] = field(default_factory=list)
    kind: str = "function"
