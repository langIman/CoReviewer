# Phase 1 实现记录

> MVP：上传 Python 文件 → 代码展示 → 选中代码段 → AI 解读 → 结果锚定到行

---

## 一、前端（React + TypeScript + Vite）

### 整体结构

```
frontend/src/
├── App.tsx                          # 根组件，左右双栏布局
├── main.tsx                         # 入口，挂载 React 根节点
├── index.css                        # 全局样式（Tailwind + highlight.js 主题）
├── types/index.ts                   # TypeScript 类型定义
├── store/useReviewStore.ts          # Zustand 全局状态管理
├── services/api.ts                  # 后端 API 调用封装
└── components/
    ├── UploadBar.tsx                 # 顶部文件上传栏
    ├── ActionBar.tsx                 # 底部操作按钮栏（AI Explain/Review/Suggest）
    ├── CodeView/CodeView.tsx         # 代码展示区（行号 + 语法高亮 + 选区检测）
    └── AIPanel/
        ├── AIPanel.tsx               # 右侧 AI 响应面板
        └── ResponseCard.tsx          # 单条 AI 响应卡片
```

### 各模块职责

**App.tsx — 布局骨架**
- 纵向：顶部 UploadBar + 下方主体区
- 主体区横向 50/50 分割：左侧 CodeView + ActionBar，右侧 AIPanel
- 使用 Tailwind 的 flex 布局，`h-screen` 撑满视口

**UploadBar.tsx — 文件上传**
- 支持点击选择和拖拽上传 `.py` 文件
- 调用 `api.uploadFile()` 发送到后端，返回文件内容后写入全局 store
- 上传成功后显示文件名和行数

**CodeView.tsx — 代码展示与选区检测**
- 将文件内容按 `\n` 拆行，逐行用 `highlight.js` 做 Python 语法高亮
- 渲染为 `<table>`，左列行号（不可选中），右列代码（可选中）
- 每行 `<tr>` 标记 `data-line={行号}`，用于选区定位
- `onMouseUp` 事件检测 `window.getSelection()`，向上遍历 DOM 找到 `data-line` 属性，计算出 `startLine`/`endLine`/`selectedText`
- 选中行标蓝色背景（`bg-blue-100`），AI 响应锚定的行标黄色背景（`bg-yellow-50`）
- 支持从 AI 面板点击行号后自动滚动到对应代码位置（`scrollIntoView`）

**ActionBar.tsx — AI 操作触发**
- 仅在有选区时显示，底部蓝色条
- 三个按钮：AI Explain / AI Review / AI Suggest
- 点击后：
  1. 生成唯一 ID，向 store 添加一条 `loading` 状态的空响应
  2. 调用 `api.streamReview()` 发起 SSE 流式请求
  3. 每收到一个 chunk，拼接到响应内容中（实时更新 UI）
  4. 流结束后标记 `loading: false`

**AIPanel.tsx — 响应列表**
- 无响应时显示引导文案
- 有响应时按时间倒序排列 ResponseCard

**ResponseCard.tsx — 单条响应卡片**
- 头部：操作类型标签（Explain/Review/Suggest）+ 可点击的行号范围（`L42-58`）
- 点击行号 → 触发左侧代码区高亮并滚动到对应位置
- 正文：使用 `react-markdown` 渲染 AI 返回的 Markdown 内容
- loading 状态显示 "thinking..." 动画

**useReviewStore.ts — 全局状态（Zustand）**
- `file`: 当前上传的文件数据
- `selection`: 当前选中的代码范围
- `responses`: AI 响应列表（最新的在前）
- `highlightLines`: 当前需要高亮的行范围（来自点击 AI 卡片）
- 上传新文件时自动清空选区和响应

**api.ts — 后端通信**
- `uploadFile(file)`: POST `/api/upload`，FormData 上传，返回文件数据
- `streamReview(params, onChunk, onDone)`: POST `/api/review`，读取 SSE 流，逐 chunk 回调

### 技术选型

| 技术 | 用途 |
|------|------|
| Vite | 开发服务器 + 构建工具，启动快，支持 HMR |
| Tailwind CSS v4 | 原子化样式，通过 `@tailwindcss/vite` 插件集成 |
| Zustand | 轻量状态管理，替代 Redux，几乎零样板代码 |
| highlight.js | Python 语法高亮，只注册 Python 语言以减小体积 |
| react-markdown | 渲染 AI 返回的 Markdown 格式内容 |

---

## 二、后端（Python FastAPI）

### 整体结构

```
backend/
├── main.py                  # FastAPI 应用入口
├── config.py                # 配置管理（环境变量）
├── requirements.txt         # Python 依赖
├── models/
│   └── schemas.py           # Pydantic 请求/响应模型
├── routers/
│   ├── file.py              # 文件上传路由
│   └── review.py            # AI 审查路由
└── services/
    ├── file_service.py      # 文件校验与存储
    ├── context.py           # Prompt 组装引擎
    └── llm.py               # LLM API 调用
```

### 各模块职责

**main.py — 应用入口**
- `load_dotenv()` 加载 `.env` 文件中的环境变量（必须在其他 import 之前）
- 创建 FastAPI 实例，配置 CORS（`allow_origins=["*"]` 允许 AutoDL 外部访问）
- 挂载 file 和 review 两个路由模块
- 提供 `/api/health` 健康检查端点

**config.py — 配置管理**
- 从环境变量读取：`QWEN_API_KEY`、`QWEN_BASE_URL`、`QWEN_MODEL`
- 文件限制：`MAX_FILE_SIZE = 1MB`，`ALLOWED_EXTENSIONS = {".py"}`
- 千问默认使用 `qwen-plus` 模型，API 地址为阿里云 DashScope 兼容端点

**routers/file.py — 文件上传**
- `POST /api/upload`：接收 `UploadFile`，校验后返回 `{ filename, content, line_count }`
- 调用 `file_service.validate_file()` 检查扩展名和文件大小
- 校验失败返回 400 错误

**routers/review.py — AI 审查**
- `POST /api/review`：接收 `ReviewRequest`，返回 SSE 流式响应
- 调用 `context.build_review_prompt()` 组装 prompt
- 调用 `llm.stream_qwen()` 获取流式文本
- 每个 chunk 包装为 `data: {JSON编码的文本}\n\n` 格式
- 流结束发送 `data: [DONE]\n\n`
- 响应头设置 `text/event-stream`，禁用缓存和缓冲

**services/file_service.py — 文件服务**
- `validate_file()`: 校验文件扩展名（仅 `.py`）和大小（≤1MB）
- `store_file()` / `get_file()`: 内存级别的文件存储（Python dict），MVP 阶段不引入数据库

**services/llm.py — LLM 调用**
- `stream_qwen()`: 异步生成器，流式调用千问 API
- 使用 OpenAI 兼容格式（`/chat/completions`），`stream: True`
- 未配置 API Key 时返回友好错误提示
- API 返回非 200 时返回错误信息（含状态码和响应体）
- 逐行解析 SSE 数据，提取 `choices[0].delta.content`

### 技术选型

| 技术 | 用途 |
|------|------|
| FastAPI | 异步 Web 框架，自带 OpenAPI 文档 |
| Pydantic | 请求/响应数据校验与序列化 |
| httpx | 异步 HTTP 客户端，支持流式请求 |
| python-dotenv | 从 `.env` 文件加载环境变量 |
| uvicorn | ASGI 服务器，`--reload` 支持热重载 |

---

## 三、核心处理逻辑（Context Engine）

### 设计理念

**CoReviewer 的核心差异化在于：用结构化的 prompt 拼装替代对话历史追加。**

传统对话式 review 的问题：
1. 每次提问都追加到对话历史，上下文越来越大，越来越多无关内容
2. AI 的注意力被稀释，后续回答质量下降
3. 用户无法精确控制 AI 看到什么

CoReviewer 的做法：
- **每次 AI 请求都是独立的**，不依赖对话历史
- 每次请求精确包含：完整文件内容 + 选中代码片段 + 行号范围 + 操作类型
- Prompt 模板按操作类型（explain/review/suggest）分别定制，引导 AI 从不同角度分析

### Prompt 模板设计

三种操作对应三个模板，结构一致但引导方向不同：

| 操作 | 引导 AI 关注的角度 |
|------|-------------------|
| explain | 功能意图、潜在问题、改进建议、上下文关系 |
| review | 正确性、安全性、可维护性、性能、最佳实践 |
| suggest | 直接给出改写代码 + 改动理由 |

每个模板都包含：
1. **完整文件内容** — 让 AI 理解全局上下文
2. **选中代码 + 行号** — 明确焦点范围
3. **结构化的分析要求** — 约束输出格式

System Prompt 固定为中文代码审查专家角色，要求 Markdown 格式输出。

### 数据流

```
用户选中代码 → 点击操作按钮
      ↓
前端组装 ReviewRequest（文件名、完整内容、选中片段、行号、操作类型）
      ↓
POST /api/review
      ↓
context.build_review_prompt() 按模板拼装 (system_prompt, user_prompt)
      ↓
llm.stream_qwen() 调用千问 API，流式返回
      ↓
SSE 格式逐 chunk 发送到前端
      ↓
前端实时拼接并渲染 Markdown，锚定到对应代码行
```

### 关键设计决策

1. **完整文件作为上下文**：MVP 阶段文件不大（≤1MB），直接传完整内容，保证 AI 能理解全局。Phase 2 将引入摘要机制处理大文件。

2. **SSE 而非 WebSocket**：单向流式够用，实现简单。后端用 `StreamingResponse` + 异步生成器，前端用 `ReadableStream` 读取。

3. **JSON 编码每个 chunk**：`data: "文本片段"` 而非 `data: 文本片段`，确保换行符、特殊字符不会破坏 SSE 协议。

4. **无状态请求**：后端不维护会话，每次请求自包含所有信息。状态全部由前端 Zustand store 管理。

---

## 四、工程配置

### 一键启动

```bash
make dev    # 同时启动前后端
```

- 后端：`uvicorn --reload --host 0.0.0.0 --port 8000`
- 前端：`vite --host 0.0.0.0 --port 6006`
- 前端通过 Vite proxy 将 `/api` 请求转发到后端 8000 端口
- 用户只需访问 6006 端口

### 环境变量（.env）

```
QWEN_API_KEY=sk-xxx         # 千问 API 密钥
QWEN_BASE_URL=https://...   # API 地址（默认 DashScope）
QWEN_MODEL=qwen-plus        # 模型名称
```
