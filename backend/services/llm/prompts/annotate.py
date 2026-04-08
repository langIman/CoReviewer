"""Prompt templates for LLM function detail analysis.

P2 design principle: LLM receives ONLY signatures + docstrings + call relationships,
never full function bodies. This drastically reduces token consumption.
"""


# ---------------------------------------------------------------------------
# Function detail: expand a single function's internal logic
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
