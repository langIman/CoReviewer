"""解析 LLM 产出的 ``code_refs`` fenced block。

对应 QA_REFACTOR_PLAN.md §2.6：约定助手答复末尾追加：

```code_refs
{ "ref_1": {"file": "a.py", "start_line": 1, "end_line": 10} }
```

本模块提供 ``parse_code_refs``：把这个 block 提出来，剩下的正文返回。

LLM 的实际行为会偏离约定，解析器需容错：
- 语言标签可能是 ``code_refs`` / ``code-refs`` / ``json`` / 无
- block 可能不在最后（尾部可能还有总结段落）
- block 可能有多个 → 取最后一个形状像 code_refs 的

识别标准："像 code_refs" = JSON object + 所有 key 形如 ``ref_\\d+``。
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


# 匹配任意 fenced block：```[lang]\n<body>\n```
_FENCE_RE = re.compile(
    r"```(\w[\w-]*)?[ \t]*\n(.*?)\n[ \t]*```",
    re.DOTALL,
)

_REF_KEY_RE = re.compile(r"^ref_\d+$")


def _looks_like_code_refs(lang: str | None, body: str) -> dict | None:
    """若 body 是 code_refs 形状的 JSON，返回解析后的 dict；否则 None。

    语言标签若明确是 ``code_refs`` / ``code-refs`` 一律认；其他语言（含 json/无）
    要求 body 解析为 object 且所有 key 匹配 ``ref_\\d+`` 才认。
    """
    raw = body.strip()
    if not raw:
        return None
    normalized_lang = (lang or "").lower().replace("-", "_")
    is_explicit = normalized_lang == "code_refs"

    if raw == "{}":
        return {} if is_explicit else None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    if not all(isinstance(v, dict) for v in parsed.values()):
        return None
    # 显式标签直接通过；否则要求 key 像 ref_N
    if is_explicit:
        return parsed
    if all(_REF_KEY_RE.match(k or "") for k in parsed.keys()):
        return parsed
    return None


def parse_code_refs(content: str) -> tuple[str, dict[str, dict]]:
    """返回 (去掉 block 后的正文, code_refs 字典)。

    - 无匹配 block → (content, {})
    - 匹配到多个 → 取最后一个
    - 解析成功 → 从正文删掉这个 fenced block 的原始区间
    """
    if not content:
        return content, {}

    last_match = None
    last_refs: dict[str, dict] | None = None
    for m in _FENCE_RE.finditer(content):
        refs = _looks_like_code_refs(m.group(1), m.group(2))
        if refs is not None:
            last_match = m
            last_refs = refs

    if last_match is None or last_refs is None:
        return content, {}

    head = content[: last_match.start()].rstrip()
    tail = content[last_match.end() :].lstrip()
    if tail:
        cleaned = f"{head}\n\n{tail}"
    else:
        cleaned = head + "\n"
    return cleaned, last_refs
