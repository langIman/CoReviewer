MODULE_SPLIT_SYSTEM = """你是一位资深软件架构师，擅长将项目按业务职责拆分为功能模块。
请用中文回答，严格按照指定的 JSON 格式输出。"""

MODULE_SPLIT_USER_TEMPLATE = """以下是项目 {project_name} 中各文件夹和文件的摘要：

{all_summaries}

{dependency_section}

以下是必须被分配到模块中的全部路径（不允许遗漏任何一个）：
{all_paths}

请根据这些信息，将项目拆分为 3-8 个功能模块。

要求：
1. 上面列出的每个路径必须且只能出现在一个模块的 paths 中（严格全覆盖，不遗漏不重复）
2. 模块按业务职责划分，而非简单的目录层级复制
3. 模块名称简洁有辨识度（2-6个字）

请严格按以下 JSON 格式输出，不要输出任何其他内容：

```json
{{
  "modules": [
    {{
      "name": "模块名称",
      "description": "一句话描述该模块的职责",
      "paths": ["路径1", "路径2"]
    }}
  ]
}}
```"""


def build_module_split_prompt(
    project_name: str,
    folder_summaries: list[dict],
    file_summaries: list[dict],
    folder_dependencies: dict[str, list[str]] | None = None,
) -> tuple[str, str]:
    # 合并文件夹摘要和根目录文件摘要
    summary_lines = []
    all_paths = []
    for s in folder_summaries:
        label = f"[文件夹] {s['path']}" if s["path"] != "." else "[根目录文件]"
        summary_lines.append(f"- {label}: {s['summary']}")
        all_paths.append(s["path"])
    for s in file_summaries:
        summary_lines.append(f"- [文件] {s['path']}: {s['summary']}")
        all_paths.append(s["path"])

    if folder_dependencies:
        dep_lines = []
        for folder, deps in sorted(folder_dependencies.items()):
            if deps:
                dep_lines.append(f"  {folder} -> {', '.join(deps)}")
        dependency_section = (
            "以下是文件夹之间的 import 依赖关系（A -> B 表示 A 中的文件导入了 B 中的文件）：\n"
            + "\n".join(dep_lines)
        )
    else:
        dependency_section = ""

    user = MODULE_SPLIT_USER_TEMPLATE.format(
        project_name=project_name,
        all_summaries="\n".join(summary_lines),
        dependency_section=dependency_section,
        all_paths="\n".join(f"  - {p}" for p in all_paths),
    )
    return MODULE_SPLIT_SYSTEM, user
