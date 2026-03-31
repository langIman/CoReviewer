"""Prompt templates for LLM semantic annotation and function detail analysis.

P2 design principle: LLM receives ONLY signatures + docstrings + call relationships,
never full function bodies. This drastically reduces token consumption.
"""


# ---------------------------------------------------------------------------
# Overview: generate a semantic flowchart from AST skeleton
# ---------------------------------------------------------------------------

OVERVIEW_SYSTEM_PROMPT = """你是一位代码架构分析专家。你的任务是将 Python 项目的调用关系骨架归纳为标准流程图，并以严格的 JSON 格式返回。

【输出格式要求 — 必须严格遵守】
1. 只返回纯 JSON，不要任何 markdown、解释、注释或其他文本
2. 不要用 ```json 包裹
3. JSON 必须包含且仅包含 "nodes" 和 "edges" 两个顶层数组
4. 每个 node 必须包含: "id"(字符串), "type"(字符串), "label"(字符串), "description"(字符串)
5. 每个 edge 必须包含且仅使用这三个字段: "source"(字符串), "target"(字符串), "label"(字符串)
6. edge 中连接节点的字段名只能是 "source" 和 "target"，禁止使用 "from"/"to" 或其他变体"""

OVERVIEW_USER_TEMPLATE = """根据以下 Python 项目的入口函数源码和辅助函数签名，将运行流程归纳为标准流程图。

注意：入口函数提供了完整源码，请根据实际代码逻辑（执行顺序、条件分支、循环等）生成流程图，不要猜测。
辅助函数只提供了签名和文档，用于理解被调用方的功能。

{skeleton}

请返回如下 JSON 结构（注意：只返回 JSON，不要任何其他内容）：

{{
  "nodes": [
    {{
      "id": "1",
      "type": "start",
      "label": "开始",
      "description": "程序入口"
    }},
    {{
      "id": "2",
      "type": "process",
      "label": "步骤名称",
      "description": "这一步做了什么",
      "file": "文件路径",
      "symbol": "函数名或类名",
      "expandable": true
    }},
    {{
      "id": "3",
      "type": "decision",
      "label": "条件判断?",
      "description": "判断什么条件"
    }},
    {{
      "id": "99",
      "type": "end",
      "label": "结束",
      "description": "程序结束"
    }}
  ],
  "edges": [
    {{
      "source": "1",
      "target": "2",
      "label": ""
    }},
    {{
      "source": "3",
      "target": "4",
      "label": "是"
    }},
    {{
      "source": "3",
      "target": "5",
      "label": "否"
    }}
  ]
}}

节点类型说明：
- "start": 程序开始（只有一个）
- "end": 程序结束（可以有多个，比如异常退出）
- "process": 处理步骤（一个有意义的操作，可能包含多个函数调用）
- "decision": 条件判断（必须有"是"和"否"两条出边）

要求：
1. 不要把每个函数都当成一个节点，而是归纳成有意义的逻辑步骤
2. 条件分支用 decision 节点表示，出边标注"是"/"否"
3. 循环用回路边表示（target 指向前面的节点）
4. process 节点如果内部逻辑复杂，设 expandable: true（表示可以展开查看子流程）
5. 节点数量根据实际复杂度决定，单层不超过 15 个
6. label 和 description 用中文
7. id 使用字符串数字 "1", "2", "3" ...
8. process 节点必须提供 file、symbol、lineStart、lineEnd 字段：
   - file: 入口函数所在的文件路径
   - symbol: 该步骤对应的核心函数名（如 register、login、add_todo），用于展开子流程
   - lineStart: 该步骤在源码中对应的起始行号（使用源码左侧的行号）
   - lineEnd: 该步骤在源码中对应的结束行号
9. 每条 edge 必须包含 "source"、"target"、"label" 三个字段，source 和 target 必须引用已有节点的 id"""


ANNOTATE_SYSTEM_PROMPT = """你是一位代码架构分析专家。你的任务是为 Python 项目的函数/类调用图生成中文语义标注。

【输出格式要求 — 必须严格遵守】
1. 只返回纯 JSON，不要任何 markdown、解释、注释或其他文本
2. 不要用 ```json 包裹
3. JSON 必须是一个对象，key 是函数的 qualified_name，value 是标注对象
4. 每个标注对象包含: "label"(简洁中文名), "description"(一句话中文描述)
5. 如果多个连续调用可以合并为一个逻辑步骤，在 "merge_group" 字段中用相同的组名标记"""

ANNOTATE_USER_TEMPLATE = """分析以下 Python 项目的调用图骨架，为每个函数/类生成中文语义标注。

项目调用图骨架：
{skeleton}

请返回如下 JSON（注意：只返回 JSON，不要任何其他内容）：

{{
  "模块路径::函数名": {{
    "label": "简洁中文名（2-6字）",
    "description": "一句话描述这个函数/类做了什么"
  }},
  ...
}}

要求：
1. label 要简洁，2-6 个中文字，如"上传文件"、"构建提示词"、"流式调用 LLM"
2. description 一句话说明功能，如"验证上传文件的格式和大小是否合法"
3. 对于内部工具函数（以 _ 开头），也要标注
4. 对于类，标注类的职责
5. 每个 qualified_name 都必须有对应的标注"""


# ---------------------------------------------------------------------------

FUNCTION_DETAIL_SYSTEM_PROMPT = """你是一位代码架构分析专家。用户想查看某个函数的内部执行逻辑。

【输出格式要求 — 必须严格遵守】
1. 只返回纯 JSON，不要任何 markdown、解释、注释或其他文本
2. 不要用 ```json 包裹
3. JSON 必须包含且仅包含 "nodes" 和 "edges" 两个顶层数组
4. 每个 node 必须包含: "id"(字符串), "type"(字符串), "label"(字符串), "description"(字符串)
5. 每个 edge 必须包含且仅使用这三个字段: "source"(字符串), "target"(字符串), "label"(字符串)
6. edge 中连接节点的字段名只能是 "source" 和 "target"，禁止使用 "from"/"to" 或其他变体"""

FUNCTION_DETAIL_USER_TEMPLATE = """用户想查看以下函数的内部执行逻辑：

函数名：{func_name}
所在文件：{file_path}
签名：{signature}
文档：{docstring}

以下是该函数的完整源码：

```python
{source_code}
```

{called_functions_section}

请将这个函数内部的逻辑展开为一个详细的子流程图，返回 JSON 格式如下：

{{
  "nodes": [
    {{"id": "1", "type": "start", "label": "函数名", "description": "..."}},
    {{"id": "2", "type": "process", "label": "...", "description": "...", "file": "文件路径", "lineStart": 行号, "lineEnd": 行号}},
    {{"id": "3", "type": "decision", "label": "条件?", "description": "..."}},
    {{"id": "99", "type": "end", "label": "返回", "description": "..."}}
  ],
  "edges": [
    {{"source": "1", "target": "2", "label": ""}},
    {{"source": "3", "target": "4", "label": "是"}},
    {{"source": "3", "target": "5", "label": "否"}}
  ]
}}

要求：
1. start 节点的 label 为函数名
2. 展开函数内部的具体逻辑步骤（参数校验、数据处理、条件判断、返回值等）
3. 条件分支用 decision 节点，出边标注"是"/"否"
4. 循环用回路边表示
5. process 节点提供精确的 file、lineStart、lineEnd
6. 节点数量根据实际复杂度决定，单层不超过 15 个
7. label 和 description 用中文
8. id 使用字符串数字 "1", "2", "3" ..."""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_annotate_prompt(graph_dict: dict) -> tuple[str, str]:
    """Build the annotation prompt from a call graph dict.

    Only sends signatures + docstrings + call relationships to LLM,
    dramatically reducing token usage compared to sending full source.
    """
    lines: list[str] = []

    # Group definitions by file
    defs_by_file: dict[str, list[dict]] = {}
    for qname, d in graph_dict.get("definitions", {}).items():
        file = d.get("file", "unknown")
        defs_by_file.setdefault(file, []).append(d)

    for file_path in sorted(defs_by_file.keys()):
        lines.append(f"\n## {file_path}")
        for d in defs_by_file[file_path]:
            qname = d["qualified_name"]
            kind = d.get("kind", "function")
            params = ", ".join(d.get("params", []))
            doc = d.get("docstring") or ""
            decorators = d.get("decorators", [])

            # Format: function_name(params) : "docstring"
            dec_str = " ".join(decorators) + " " if decorators else ""
            sig = f"  {dec_str}{kind} {d['name']}({params})"
            if doc:
                sig += f'  # "{doc}"'
            lines.append(sig)

    # Add call relationships
    edges = graph_dict.get("edges", [])
    resolved_edges = [e for e in edges if e.get("callee_resolved")]
    if resolved_edges:
        lines.append("\n## 调用关系")
        for e in resolved_edges:
            caller = e["caller"].split("::")[-1] if "::" in e["caller"] else e["caller"]
            callee = e["callee_resolved"].split("::")[-1] if "::" in e["callee_resolved"] else e["callee_resolved"]
            lines.append(f"  {caller} → {callee}")

    skeleton = "\n".join(lines)
    user_prompt = ANNOTATE_USER_TEMPLATE.format(skeleton=skeleton)
    return ANNOTATE_SYSTEM_PROMPT, user_prompt


def build_function_detail_prompt(
    func_name: str,
    file_path: str,
    signature: str,
    docstring: str,
    source_code: str,
    called_functions: list[dict] | None = None,
) -> tuple[str, str]:
    """Build prompt for expanding a function's internal logic.

    Only sends the single target function's code + signatures of called functions.
    """
    # Build section about called functions
    called_section = ""
    if called_functions:
        parts = ["该函数调用了以下函数（仅签名）：\n"]
        for cf in called_functions:
            params = ", ".join(cf.get("params", []))
            doc = cf.get("docstring") or ""
            line = f"- {cf['name']}({params})"
            if doc:
                line += f'  # "{doc}"'
            parts.append(line)
        called_section = "\n".join(parts)

    user_prompt = FUNCTION_DETAIL_USER_TEMPLATE.format(
        func_name=func_name,
        file_path=file_path,
        signature=signature,
        docstring=docstring or "无",
        source_code=source_code,
        called_functions_section=called_section,
    )
    return FUNCTION_DETAIL_SYSTEM_PROMPT, user_prompt


def _format_skeleton(graph_dict: dict, project_files: dict[str, str]) -> str:
    """Format call graph dict into a compact skeleton for LLM consumption.

    Entry point functions include full source code so LLM can understand
    the actual execution flow. Non-entry functions only include signatures.
    """
    lines: list[str] = []

    defs = graph_dict.get("definitions", {})
    edges = graph_dict.get("edges", [])

    # Show entry points with full source code
    entry_defs = {k: v for k, v in defs.items() if v.get("is_entry")}
    if entry_defs:
        lines.append("## 入口函数源码")
        for qname, d in entry_defs.items():
            source = project_files.get(d["file"], "")
            if source:
                source_lines = source.split("\n")
                # Include line numbers so LLM can reference exact call sites
                numbered_lines = []
                for i in range(d["line_start"] - 1, d["line_end"]):
                    numbered_lines.append(f"{i + 1:>4}| {source_lines[i]}")
                func_code = "\n".join(numbered_lines)
                lines.append(f"\n### {d['name']}  [{d['file']}]")
                lines.append(f"```python\n{func_code}\n```")
            else:
                # Fallback: no source available, show signature
                params = ", ".join(d.get("params", []))
                lines.append(f"  {d['kind']} {d['name']}({params})  [{d['file']}]")

    # Group other definitions by file
    defs_by_file: dict[str, list[dict]] = {}
    for qname, d in defs.items():
        if d.get("is_entry"):
            continue
        file = d.get("file", "unknown")
        defs_by_file.setdefault(file, []).append(d)

    for file_path in sorted(defs_by_file.keys()):
        lines.append(f"\n## {file_path}")
        for d in defs_by_file[file_path]:
            params = ", ".join(d.get("params", []))
            doc = d.get("docstring") or ""
            sig = f"  {d['kind']} {d['name']}({params})"
            if doc:
                sig += f'  # "{doc}"'
            lines.append(sig)

    # Add resolved call relationships
    resolved = [e for e in edges if e.get("callee_resolved")]
    if resolved:
        # Deduplicate: same caller → callee pair
        seen: set[tuple[str, str]] = set()
        lines.append("\n## 调用关系")
        for e in resolved:
            caller = e["caller"].split("::")[-1] if "::" in e["caller"] else e["caller"]
            callee = e["callee_resolved"].split("::")[-1] if "::" in e["callee_resolved"] else e["callee_resolved"]
            key = (caller, callee)
            if key not in seen:
                seen.add(key)
                lines.append(f"  {caller} → {callee}")

    return "\n".join(lines)


def build_overview_prompt(graph_dict: dict, project_files: dict[str, str]) -> tuple[str, str]:
    """Build the semantic overview flowchart prompt.

    Entry point functions include full source code so LLM understands the
    actual execution flow. Non-entry functions only include signatures
    as context for what called functions do.
    """
    skeleton = _format_skeleton(graph_dict, project_files)
    user_prompt = OVERVIEW_USER_TEMPLATE.format(skeleton=skeleton)
    return OVERVIEW_SYSTEM_PROMPT, user_prompt

