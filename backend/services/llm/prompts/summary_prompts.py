FILE_SUMMARY_SYSTEM = "你是一位代码分析专家，擅长快速理解代码文件的职责。请用中文回答。"

FILE_SUMMARY_USER_TEMPLATE = """以下是文件 {file_path} 的部分代码片段（包含各函数和类的前几行）。
请根据这些片段，用一段简洁的话概括这个文件的职责和作用。
只需要描述它做什么，不要复述代码内容。
如果你认为提供的代码片段不足以判断该文件的职责，请直接输出"信息不足无法推测"，不需要任何其他回答。

{extracted_code}"""

FOLDER_SUMMARY_SYSTEM = "你是一位资深软件架构师，擅长理解模块的整体职责。请用中文回答。"

FOLDER_SUMMARY_USER_TEMPLATE = """以下是文件夹 {folder_path} 中各文件和子文件夹的摘要：

{summaries}

请根据这些摘要，用一段话概括这个文件夹的整体职责和作用。
只需要描述它做什么，不要逐个复述各文件的摘要。
如果你认为提供的摘要信息不足以判断该文件夹的职责，请直接输出"信息不足无法推测"，不需要任何其他回答。"""

PROJECT_SUMMARY_SYSTEM = """你是一位资深软件架构师，擅长快速理解项目全貌并生成清晰的项目概述。
请用中文回答，使用 Markdown 格式，严格按照指定的输出模板。"""

PROJECT_SUMMARY_USER_TEMPLATE = """以下是项目 {project_name} 中各文件夹和文件的摘要：

{summaries}

请根据这些摘要，按照以下模板生成项目概述：

## {project_name}

> 一句话定位（简洁描述项目是什么）

### 项目定位
2-3句话描述项目解决什么问题、面向谁。

### 核心能力
- **能力名称**：简要说明
- **能力名称**：简要说明
（列出3-5个核心能力）

### 技术架构
- 后端：xxx
- 前端：xxx
- 其他关键技术组件

要求：
1. 严格按照上面的模板格式输出
2. 内容简洁有层次，面向用户展示
3. 不要逐个复述各文件夹的摘要
4. 如果你认为提供的摘要信息不足以判断该项目的职责，请直接输出"信息不足无法推测"，不需要任何其他回答。"""


def build_file_summary_prompt(file_path: str, extracted_code: str) -> tuple[str, str]:
    user = FILE_SUMMARY_USER_TEMPLATE.format(file_path=file_path, extracted_code=extracted_code)
    return FILE_SUMMARY_SYSTEM, user


def build_folder_summary_prompt(folder_path: str, file_summaries: list[tuple[str, str]]) -> tuple[str, str]:
    summaries = "\n".join(f"{name}: {summary}" for name, summary in file_summaries)
    user = FOLDER_SUMMARY_USER_TEMPLATE.format(folder_path=folder_path, summaries=summaries)
    return FOLDER_SUMMARY_SYSTEM, user


def build_project_summary_prompt(project_name: str, folder_summaries: list[tuple[str, str]]) -> tuple[str, str]:
    summaries = "\n".join(f"{name}: {summary}" for name, summary in folder_summaries)
    user = PROJECT_SUMMARY_USER_TEMPLATE.format(project_name=project_name, summaries=summaries)
    return PROJECT_SUMMARY_SYSTEM, user
