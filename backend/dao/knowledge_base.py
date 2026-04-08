"""知识库 DAO — Worker 产出的函数摘要存取。

Per-request 内存存储，无锁设计（asyncio 单线程，put() 无 await）。
每次请求新建实例，请求结束即 GC。
"""

from backend.models.agent_models import FunctionSummary


class KnowledgeBase:
    """函数摘要的内存存取。"""

    def __init__(self) -> None:
        self._entries: dict[str, FunctionSummary] = {}

    def put(self, summary: FunctionSummary) -> None:
        self._entries[summary.qualified_name] = summary

    def format_for_prompt(self) -> str:
        """格式化为 Lead prompt 中的辅助函数语义摘要。

        输出示例：
        - AuthService.register(self, username, email, password): 验证邮箱和密码格式，创建 User 存入内存
        - AuthService.login(self, username, password): 校验密码，生成 token
        """
        lines: list[str] = []
        for s in sorted(self._entries.values(), key=lambda x: x.qualified_name):
            short_name = s.qualified_name.split("::")[-1] if "::" in s.qualified_name else s.qualified_name
            params_str = ", ".join(s.params)
            lines.append(f"- {short_name}({params_str}): {s.summary}")
        return "\n".join(lines)
