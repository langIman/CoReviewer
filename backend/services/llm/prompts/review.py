from backend.models.schemas import ReviewRequest
from backend.dao.file_store import get_project_summary

SYSTEM_PROMPT = """你是一位资深代码审查专家，擅长 Python 开发。
你的回答应当结构清晰、直击要点，使用中文回答。使用 Markdown 格式。
如果提供了相关文件，请在分析时考虑跨文件的依赖关系。"""

ACTION_TEMPLATES = {
    "explain": """以下是一个 Python 文件的完整内容，用户选中了第 {start_line}-{end_line} 行的代码，请对选中部分进行解读。

## 完整文件：{file_name}
```python
{full_content}
```

## 选中代码（第 {start_line}-{end_line} 行）
```python
{selected_code}
```

请从以下角度分析：
1. **功能与意图**：这段代码在做什么
2. **上下文关系**：与文件中其他部分的依赖""",
}


def build_review_prompt(req: ReviewRequest) -> tuple[str, str]:
    """组装结构化 prompt，返回 (system_prompt, user_prompt)。"""
    template = ACTION_TEMPLATES.get(req.action, ACTION_TEMPLATES["explain"])
    user_prompt = template.format(
        file_name=req.file_name,
        full_content=req.full_content,
        selected_code=req.selected_code,
        start_line=req.start_line,
        end_line=req.end_line,
    )

    # 项目模式下注入项目摘要
    if req.project_mode:
        summary = get_project_summary()
        if summary:
            user_prompt = f"## 项目全局摘要\n{summary}\n\n{user_prompt}"

    # 追加相关文件上下文
    if req.related_files:
        context_block = "\n\n## 相关文件（通过 import 分析）\n"
        for rf in req.related_files:
            context_block += f"\n### {rf.path}\n```python\n{rf.content}\n```\n"
        user_prompt += context_block

    return SYSTEM_PROMPT, user_prompt
