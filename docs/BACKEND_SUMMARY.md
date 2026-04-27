# 后端内容简要总结

## 1. 后端定位

本项目后端是一个基于 FastAPI 的代码理解服务，负责接收前端上传的项目源码，完成静态分析、摘要生成、模块划分、Wiki 文档生成和代码问答。整体目标是把一个代码仓库转成可浏览、可检索、可问答的知识结构。

后端入口是 `backend/main.py`，启动时会：

- 加载 `.env` 中的 Qwen API 配置。
- 初始化 FastAPI 应用和 CORS。
- 注册文件、Wiki、QA 三组路由。
- 初始化 SQLite 数据库 `backend/data/summaries.db`。

## 2. 目录结构

```text
backend/
  controllers/       HTTP 接口层，负责请求/响应和后台任务调度
  services/          业务编排层，包含上传初始化、摘要、模块划分、Wiki、QA、Agent
  dao/               数据访问层，读写 SQLite 或进程内项目文件
  models/            Pydantic/dataclass 数据模型
  utils/analysis/    静态分析能力，构建符号表、调用图、模块依赖
  services/llm/      Qwen/OpenAI-compatible 调用封装和 prompt 模板
```

## 3. 对外接口

### 文件与项目

- `POST /api/file/upload`：上传单个文件，做格式和大小校验后暂存。
- `POST /api/file/upload-project`：上传整个项目，过滤允许的文件类型，写入内存项目存储，并触发项目初始化。
- `POST /api/file/project/summary`：基于当前项目生成项目摘要。

### Wiki

- `POST /api/wiki/generate`：创建后台生成任务，返回 `task_id`。
- `GET /api/wiki/status/{task_id}`：查询 Wiki 生成状态。
- `GET /api/wiki/{project_name}`：读取完整 `WikiDocument`。
- `GET /api/wiki/{project_name}/export`：导出整份 Wiki 为 Markdown。

### QA

- `POST /api/qa/ask`：SSE 流式问答入口，支持 `fast` 和 `deep` 两种模式。
- `GET /api/qa/conversations`：列出项目会话。
- `GET /api/qa/conversations/{id}`：读取会话详情。
- `DELETE /api/qa/conversations/{id}`：删除会话。

## 4. 核心数据流

### 4.1 项目上传与初始化

上传项目后，`file_service.upload_project_files()` 会筛选源码和文档文件，并把当前项目文件放进进程内的 `file_store`。随后调用 `initialize_project()` 完成初始化：

1. 清空该项目旧的 AST、摘要、Wiki 数据。
2. 失效内存 AST 缓存。
3. 重新构建 AST 静态分析结果。
4. 将符号表、调用边和模块信息写入 SQLite。

这里的“项目源码原文”主要保存在内存里，派生数据保存在 SQLite 中。

### 4.2 静态分析

静态分析由 `utils/analysis/ast_service.py` 编排，核心产物是 `ProjectAST`：

- `definitions`：函数、类、方法等符号定义。
- `edges`：函数调用关系。
- `modules`：文件级模块节点，包含行数、符号数和 imports。
- `entry_points`：识别出的入口点。

分析流程支持 Python、Java、Rust 等 AST 文件类型。Python 使用内置 `ast`，其他语言通过 tree-sitter 解析。调用边解析优先使用 import 关系，解析不到时会用简单名唯一匹配作为兜底。

### 4.3 摘要生成

摘要由 `summary_service.generate_hierarchical_summary()` 负责，采用自底向上的方式：

1. 对每个文件抽取 skeleton，调用 LLM 生成文件摘要。
2. 按文件夹聚合子文件和子文件夹摘要，生成文件夹摘要。
3. 汇总顶层摘要，生成项目摘要。

摘要会存入 SQLite 的 `summaries` 表。后续模块划分、Wiki 生成和 QA 都会复用这些摘要，避免重复读取全量源码。

### 4.4 模块划分

模块划分由 `module_service.generate_module_split()` 触发。它使用通用 Agent 框架和 `ModuleSplitSkill`，让 LLM 在工具辅助下读取项目摘要、符号、模块等信息，最后输出：

```json
{
  "modules": [
    {
      "name": "模块名",
      "description": "模块描述",
      "paths": ["文件路径"]
    }
  ]
}
```

如果第一次输出不是合法 JSON，会追加一次严格 JSON 重试。

### 4.5 Wiki 生成

Wiki 生成入口是 `wiki_service.generate_wiki()`，是一个 eager 生成流程，也就是一次性生成所有页面。主要步骤是：

1. 根据项目文件内容计算 hash，命中缓存时直接返回已有 Wiki。
2. 确保 AST 和文件摘要可用。
3. 调用模块划分，并过滤到 AST 覆盖的文件。
4. 收集 README、配置、运行线索和项目统计。
5. 调用 Outliner 生成核心架构章节和专题议题。
6. 并发生成模块页、章节页、专题页。
7. 生成 overview 首页。
8. 构建导航索引树。
9. 将 `WikiDocument` 和所有 `WikiPage` 保存到 SQLite。

Wiki 页面分为：

- `overview`：项目首页。
- `category`：侧边栏分组页。
- `chapter`：核心架构文章。
- `module`：模块详解页。
- `topic`：专题深入文章。

页面中会保留 `outgoing_links` 和 `code_refs`，前端可用它们完成 Wiki 跳转和代码定位。

### 4.6 QA 问答

QA 由 `qa_service.answer()` 统一编排，输出 SSE 事件流，并在结束后保存用户消息和助手消息。

`fast` 模式：

- 使用 BM25 从符号表中检索相关函数/类。
- 拼入 Wiki 大纲、模块列表、相关文件摘要、Top-K 符号源码。
- 调用流式 LLM，直接把 token 推给前端。

`deep` 模式：

- 使用工具循环，让模型按需调用工具。
- 工具包括摘要读取、模块读取、符号读取、调用边读取、文件内容读取、代码搜索等。
- 有最大迭代次数和 token 预算两道安全阀。
- 非流式最终答复会被切片成伪流式输出。

QA 会话和消息存入 SQLite，消息可携带工具事件和代码引用。

## 5. 持久化设计

SQLite 文件路径是 `backend/data/summaries.db`，主要表包括：

- `summaries`：文件、文件夹、项目摘要。
- `symbols`：静态分析得到的符号定义。
- `call_edges`：调用关系。
- `modules`：文件级模块信息。
- `wiki_documents`：Wiki 项目元数据、hash、索引。
- `wiki_pages`：每个 Wiki 页面内容和元数据。
- `qa_conversations`：QA 会话。
- `qa_messages`：QA 消息、工具事件、代码引用。

项目文件内容本身保存在 `dao/file_store.py` 的进程内字典中，因此服务重启后需要重新上传项目，才能完整支持源码读取和基于源码的 QA。

## 6. LLM 与 Agent 层

LLM 调用集中在 `services/llm/llm_service.py`，通过 OpenAI-compatible 的 `/chat/completions` 接口访问 Qwen。该层提供：

- `call_qwen()`：非流式 system/user 调用。
- `stream_qwen()`：非工具的流式调用。
- `stream_messages()`：完整 messages 的流式调用。
- `call_llm()`：支持 tools 的非流式调用。

配置项主要来自 `.env`：

- `QWEN_API_KEY`
- `QWEN_BASE_URL`
- `QWEN_MODEL`
- `QWEN_ENABLE_THINKING`

Agent 框架在 `services/agent/agent.py`，核心循环是“模型决策 -> 工具执行 -> 工具结果注入 -> 继续或停止”。模块划分和 deep QA 都复用了这套工具调用思路。

## 7. 当前特点与注意事项

- 后端主流程偏“生成型”：上传项目后先构建 AST 和摘要，再用 LLM 生成 Wiki 和回答问题。
- SQLite 缓存了大部分派生数据，但项目源码原文仍是进程内存储。
- Wiki 任务状态是进程内字典，适合 MVP；多进程或重启后任务状态不会保留。
- Wiki 生成是 eager 模式，首次生成会比较慢，但读取已生成 Wiki 很快。
- Qwen3.x 的 thinking 会明显影响延迟，模板化任务通常会显式关闭 thinking。
- deep QA 能查更多上下文，但成本和延迟都高于 fast QA。

## 8. 一句话总结

后端把“上传的代码项目”转成三类知识资产：静态分析图、结构化 Wiki、可追踪代码引用的 QA 会话。静态分析负责提供可靠代码坐标，摘要和模块划分负责压缩上下文，Wiki 和 QA 则是面向用户的两种消费方式。
