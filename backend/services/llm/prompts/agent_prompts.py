"""Lead Agent / Worker Agent 的 Prompt 模板。"""


# ---------------------------------------------------------------------------
# Worker: 函数语义摘要
# ---------------------------------------------------------------------------

WORKER_SYSTEM_PROMPT = (
    "你是一位代码分析助手。请用1-2句中文简洁描述给定函数的功能。"
    "只返回描述文本，不要返回任何 JSON、Markdown 或其他格式。"
)

WORKER_USER_TEMPLATE = """函数名：{func_name}
所在文件：{file_path}
签名：{signature}

源码：
```python
{source_code}
```

请用1-2句话描述这个函数做了什么。"""


def build_worker_prompt(
    func_name: str,
    file_path: str,
    signature: str,
    source_code: str,
) -> tuple[str, str]:
    """构建 Worker 的函数摘要 prompt。"""
    user_prompt = WORKER_USER_TEMPLATE.format(
        func_name=func_name,
        file_path=file_path,
        signature=signature,
        source_code=source_code,
    )
    return WORKER_SYSTEM_PROMPT, user_prompt


# ---------------------------------------------------------------------------
# Lead: 基于核心函数源码 + KB 摘要生成流程图
# ---------------------------------------------------------------------------

LEAD_SYSTEM_PROMPT = """你是一位代码架构分析专家。你的任务是将 Python 项目的核心函数逻辑归纳为标准流程图，并以严格的 JSON 格式返回。

【输出格式要求 — 必须严格遵守】
1. 只返回纯 JSON，不要任何 markdown、解释、注释或其他文本
2. 不要用 ```json 包裹
3. JSON 必须包含且仅包含 "nodes" 和 "edges" 两个顶层数组
4. 每个 node 必须包含: "id"(字符串), "type"(字符串), "label"(字符串), "description"(字符串)
5. 每个 edge 必须包含且仅使用这三个字段: "source"(字符串), "target"(字符串), "label"(字符串)
6. edge 中连接节点的字段名只能是 "source" 和 "target"，禁止使用 "from"/"to" 或其他变体"""

LEAD_USER_TEMPLATE = """根据以下核心函数源码和辅助函数语义摘要，将运行流程归纳为标准流程图。

注意：核心函数提供了完整源码，请根据实际代码逻辑（执行顺序、条件分支、循环等）生成流程图，不要猜测。
辅助函数的语义摘要由 AI 分析源码后生成，描述了每个被调函数的实际功能，请据此理解被调用方的行为。

## 核心函数源码 [{file_path}]

```python
{key_function_source}
```

## 辅助函数语义摘要

{kb_summaries}

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
   - file: 核心函数所在的文件路径
   - symbol: 该步骤对应的核心函数名（如 register、login、add_todo），用于展开子流程
   - lineStart: 该步骤在源码中对应的起始行号（使用源码左侧的行号）
   - lineEnd: 该步骤在源码中对应的结束行号
9. 每条 edge 必须包含 "source"、"target"、"label" 三个字段，source 和 target 必须引用已有节点的 id"""


def build_lead_prompt(
    file_path: str,
    key_function_source: str,
    kb_summaries: str,
) -> tuple[str, str]:
    """构建 Lead Agent 的流程图生成 prompt。"""
    user_prompt = LEAD_USER_TEMPLATE.format(
        file_path=file_path,
        key_function_source=key_function_source,
        kb_summaries=kb_summaries if kb_summaries else "(无辅助函数)",
    )
    return LEAD_SYSTEM_PROMPT, user_prompt
