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
2. **潜在问题**：bug、边界情况、性能隐患
3. **改进建议**：如何写得更好
4. **上下文关系**：与文件中其他部分的依赖""",
    "review": """以下是一个 Python 文件，请对用户选中的第 {start_line}-{end_line} 行代码进行严格审查。

## 完整文件：{file_name}
```python
{full_content}
```

## 选中代码（第 {start_line}-{end_line} 行）
```python
{selected_code}
```

请按以下维度逐项审查：
1. **正确性**：逻辑是否正确
2. **安全性**：是否存在安全隐患
3. **可维护性**：命名、结构是否清晰
4. **性能**：是否有优化空间
5. **最佳实践**：是否符合 Python 惯用写法""",
    "suggest": """以下是一个 Python 文件，用户选中了第 {start_line}-{end_line} 行代码，请给出改写建议。

## 完整文件：{file_name}
```python
{full_content}
```

## 选中代码（第 {start_line}-{end_line} 行）
```python
{selected_code}
```

请直接给出改写后的代码，并简要说明改动理由。""",
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
