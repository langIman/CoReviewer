FLOWCHART_SYSTEM_PROMPT = """你是一位代码架构分析专家。你的任务是将 Python 项目的运行流程归纳为标准流程图，并以严格的 JSON 格式返回。

【输出格式要求 — 必须严格遵守】
1. 只返回纯 JSON，不要任何 markdown、解释、注释或其他文本
2. 不要用 ```json 包裹
3. JSON 必须包含且仅包含 "nodes" 和 "edges" 两个顶层数组
4. 每个 node 必须包含: "id"(字符串), "type"(字符串), "label"(字符串), "description"(字符串)
5. 每个 edge 必须包含且仅使用这三个字段: "source"(字符串), "target"(字符串), "label"(字符串)
6. edge 中连接节点的字段名只能是 "source" 和 "target"，禁止使用 "from"/"to" 或其他变体"""

FLOWCHART_USER_TEMPLATE = """分析以下 Python 项目，从程序入口开始，将运行流程归纳为标准流程图。

{file_contents}

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
      "code_snippet": "该步骤对应的一行关键代码（从源码中复制）",
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
8. process 节点必须提供 file、symbol、code_snippet 三个字段：
   - file: 该步骤发生所在的文件路径（通常是调用方文件）
   - symbol: 该步骤对应的函数名或类名
   - code_snippet: 从源码中原样复制的一行关键代码（优先复制调用语句，而非函数定义语句）
   注意：不要返回 line 字段，行号会由系统自动解析
9. 每条 edge 必须包含 "source"、"target"、"label" 三个字段，source 和 target 必须引用已有节点的 id"""


DETAIL_SYSTEM_PROMPT = """你是一位代码架构分析专家。用户想查看某个流程步骤的详细子流程。

【输出格式要求 — 必须严格遵守】
1. 只返回纯 JSON，不要任何 markdown、解释、注释或其他文本
2. 不要用 ```json 包裹
3. JSON 必须包含且仅包含 "nodes" 和 "edges" 两个顶层数组
4. 每个 node 必须包含: "id"(字符串), "type"(字符串), "label"(字符串), "description"(字符串)
5. 每个 edge 必须包含且仅使用这三个字段: "source"(字符串), "target"(字符串), "label"(字符串)
6. edge 中连接节点的字段名只能是 "source" 和 "target"，禁止使用 "from"/"to" 或其他变体"""

DETAIL_USER_TEMPLATE = """用户想展开查看以下步骤的详细子流程：

步骤名称：{step_label}
步骤描述：{step_description}
所在文件：{step_file}
对应符号：{step_symbol}

以下是相关的项目代码：

{file_contents}

请将这个步骤内部的逻辑展开为一个详细的子流程图，返回 JSON 格式如下：

{{
  "nodes": [
    {{"id": "1", "type": "start", "label": "步骤名称", "description": "..."}},
    {{"id": "2", "type": "process", "label": "...", "description": "...", "file": "文件路径", "symbol": "函数名", "code_snippet": "源码中的一行关键代码", "expandable": false}},
    {{"id": "3", "type": "decision", "label": "条件?", "description": "..."}},
    {{"id": "99", "type": "end", "label": "结束", "description": "..."}}
  ],
  "edges": [
    {{"source": "1", "target": "2", "label": ""}},
    {{"source": "3", "target": "4", "label": "是"}},
    {{"source": "3", "target": "5", "label": "否"}}
  ]
}}

要求：
1. start 节点的 label 为步骤名称
2. 展开这个步骤内部的具体逻辑，比如参数校验、数据库操作、条件判断等
3. 如果子步骤内部仍然复杂，设 expandable: true
4. 节点数量根据实际复杂度决定，单层不超过 15 个
5. label 和 description 用中文
6. id 使用字符串数字 "1", "2", "3" ...
7. process 节点必须提供 file、symbol、code_snippet 三个字段：
   - file: 该步骤发生所在的文件路径
   - symbol: 该步骤对应的函数名或类名
   - code_snippet: 从源码中原样复制的一行关键代码（优先复制调用语句）
   注意：不要返回 line 字段，行号会由系统自动解析
8. 每条 edge 必须包含 "source"、"target"、"label" 三个字段，source 和 target 必须引用已有节点的 id"""


def _format_project_files(project_files: dict[str, str]) -> str:
    """将项目文件拼接为 prompt 内容。"""
    parts = []
    for path in sorted(project_files.keys()):
        content = project_files[path]
        lines = content.split("\n")
        if len(lines) > 150:
            content = "\n".join(lines[:150]) + f"\n# ... (truncated, {len(lines)} lines)"
        parts.append(f"### {path}\n```python\n{content}\n```")
    return "\n\n".join(parts)


def build_flowchart_prompt(project_files: dict[str, str]) -> tuple[str, str]:
    """构建主流程图的 prompt。"""
    file_contents = _format_project_files(project_files)
    user_prompt = FLOWCHART_USER_TEMPLATE.format(file_contents=file_contents)
    return FLOWCHART_SYSTEM_PROMPT, user_prompt


def build_detail_prompt(
    step_label: str,
    step_description: str,
    step_file: str,
    step_symbol: str,
    project_files: dict[str, str],
) -> tuple[str, str]:
    """构建子流程展开的 prompt。"""
    file_contents = _format_project_files(project_files)
    user_prompt = DETAIL_USER_TEMPLATE.format(
        step_label=step_label,
        step_description=step_description,
        step_file=step_file or "未知",
        step_symbol=step_symbol or "未知",
        file_contents=file_contents,
    )
    return DETAIL_SYSTEM_PROMPT, user_prompt
