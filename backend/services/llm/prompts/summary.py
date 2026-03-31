SUMMARY_SYSTEM_PROMPT = "你是一位资深软件架构师，擅长快速理解项目全貌。请用中文回答，使用 Markdown 格式。"

SUMMARY_USER_TEMPLATE = """请对以下 Python 项目进行全面分析，生成一份简洁的项目摘要。

项目名称：{project_name}
文件列表：{file_list}

{file_contents}

请从以下维度总结（控制在 300 字以内）：
1. **项目目的**：这个项目是做什么的
2. **架构概览**：模块划分和职责
3. **核心数据流**：主要的调用链路
4. **关键设计决策**：使用的模式和约定
5. **技术栈**：依赖的库和框架"""


def build_summary_prompt(project_name: str, project_files: dict[str, str]) -> tuple[str, str]:
    """构建项目摘要的 prompt。"""
    file_list = ", ".join(sorted(project_files.keys()))
    parts = []
    for path in sorted(project_files.keys()):
        content = project_files[path]
        lines = content.split("\n")
        if len(lines) > 150:
            content = "\n".join(lines[:150]) + f"\n# ... (truncated, {len(lines)} lines total)"
        parts.append(f"### {path}\n```python\n{content}\n```")

    file_contents = "\n\n".join(parts)
    user_prompt = SUMMARY_USER_TEMPLATE.format(
        project_name=project_name,
        file_list=file_list,
        file_contents=file_contents,
    )
    return SUMMARY_SYSTEM_PROMPT, user_prompt
