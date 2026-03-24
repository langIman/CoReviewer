FLOWCHART_SYSTEM_PROMPT = """你是一位代码架构分析专家。你的任务是将 Python 项目的运行流程归纳为标准流程图，并以严格的 JSON 格式返回。
你必须只返回 JSON，不要返回任何 markdown、解释或其他文本。不要用 ```json 包裹。"""

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
      "line": 行号,
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
8. file 和 line 字段只在 process 节点上提供（指向最相关的代码位置）"""


DETAIL_SYSTEM_PROMPT = """你是一位代码架构分析专家。用户想查看某个流程步骤的详细子流程。
你必须只返回 JSON，不要返回任何 markdown、解释或其他文本。不要用 ```json 包裹。"""

DETAIL_USER_TEMPLATE = """用户想展开查看以下步骤的详细子流程：

步骤名称：{step_label}
步骤描述：{step_description}
所在文件：{step_file}
所在行号：{step_line}

以下是相关的项目代码：

{file_contents}

请将这个步骤内部的逻辑展开为一个详细的子流程图，返回格式与主流程图相同（包含 start/end/process/decision 节点）。

要求：
1. start 节点的 label 为步骤名称
2. 展开这个步骤内部的具体逻辑，比如参数校验、数据库操作、条件判断等
3. 如果子步骤内部仍然复杂，设 expandable: true
4. 节点数量根据实际复杂度决定，单层不超过 15 个
5. label 和 description 用中文"""


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
    step_line: int,
    project_files: dict[str, str],
) -> tuple[str, str]:
    """构建子流程展开的 prompt。"""
    file_contents = _format_project_files(project_files)
    user_prompt = DETAIL_USER_TEMPLATE.format(
        step_label=step_label,
        step_description=step_description,
        step_file=step_file or "未知",
        step_line=step_line or 0,
        file_contents=file_contents,
    )
    return DETAIL_SYSTEM_PROMPT, user_prompt
