# CoReviewer 开发路线图

> 用结构化 UI 交互替代自由对话，实现更精准的代码审查上下文管理。

---

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                    Browser (React)                   │
│                                                      │
│  ┌──────────────────────┬──────────────────────────┐ │
│  │     Left Panel       │      Right Panel         │ │
│  │                      │                          │ │
│  │  [File Tree]         │  [AI Response Panel]     │ │
│  │  [Code View]         │   - Module Overview      │ │
│  │   - Line Numbers     │   - Selection Analysis   │ │
│  │   - Syntax Highlight │   - Review Items         │ │
│  │   - Selection        │   - Export Actions       │ │
│  │   - Inline Markers   │                          │ │
│  └──────────┬───────────┴────────────┬─────────────┘ │
│             │    REST / WebSocket     │               │
└─────────────┼────────────────────────┼───────────────┘
              │                        │
┌─────────────┼────────────────────────┼───────────────┐
│             ▼     FastAPI Backend     ▼               │
│                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ File Service│  │Context Engine│  │ LLM Adapter │  │
│  │ - Upload    │  │ - Summary    │  │ - Qwen      │  │
│  │ - Parse     │  │ - Focus      │  │ - Doubao    │  │
│  │ - AST       │  │ - Assemble   │  │ - GLM       │  │
│  └─────────────┘  └──────────────┘  └──────┬──────┘  │
│                                            │         │
│  ┌─────────────────────────────────────────┘         │
│  │  ┌──────────┐                                     │
│  └─▶│ SQLite   │  (Phase 2+)                         │
│     └──────────┘                                     │
└───────────────────────────────────────────────────────┘
```

---

## Phase 1：MVP — 核心验证（当前阶段）

**目标：证明"结构化 UI 交互 + 精准上下文"比自由对话更好用。**

一句话描述：上传一个 Python 文件 → 展示带行号语法高亮的代码 → 鼠标选中代码段 → AI 给出针对性解读 → 结果锚定到对应代码行。

### 1.1 项目骨架搭建

**后端（FastAPI）**

```
backend/
├── main.py              # FastAPI 入口，CORS 配置，路由挂载
├── routers/
│   ├── file.py          # POST /api/upload — 接收文件，返回文件内容+元数据
│   └── review.py        # POST /api/review — 接收选中代码+上下文，返回 AI 解读
├── services/
│   ├── file_service.py  # 文件读取、临时存储、基础元信息提取
│   ├── context.py       # 上下文组装引擎（Phase 1 仅拼接文件摘要+选中片段）
│   └── llm.py           # LLM 调用抽象层 — Phase 1 只实现 Qwen adapter
├── models/
│   └── schemas.py       # Pydantic 请求/响应模型
├── config.py            # 配置管理（API key 从环境变量读取）
└── requirements.txt
```

**前端（React + Vite）**

```
frontend/
├── src/
│   ├── App.tsx                    # 根组件，双栏布局
│   ├── components/
│   │   ├── CodeView/
│   │   │   ├── CodeView.tsx       # 代码展示区（<pre> + 行号 + highlight.js）
│   │   │   └── SelectionHandler.ts # 选区检测，映射到行号范围
│   │   ├── AIPanel/
│   │   │   ├── AIPanel.tsx        # 右侧 AI 响应面板
│   │   │   └── ResponseCard.tsx   # 单条 AI 响应卡片（锚定到行号范围）
│   │   └── UploadBar.tsx          # 文件上传入口
│   ├── services/
│   │   └── api.ts                 # 后端 API 调用封装
│   ├── store/
│   │   └── useReviewStore.ts      # Zustand 状态管理
│   └── types/
│       └── index.ts               # TypeScript 类型定义
├── index.html
├── package.json
├── vite.config.ts
└── tsconfig.json
```

### 1.2 核心功能拆解

#### F1 · 文件上传与展示

- 前端：拖拽/点击上传 `.py` 文件
- 后端：接收文件，返回 `{ filename, content, line_count }`
- 前端：使用 `highlight.js`（Python 语法）渲染代码，左侧显示行号
- **不做**：文件持久化。文件存内存，页面刷新即丢失

#### F2 · 代码选区检测

- 用户鼠标选中一段代码
- 前端检测 `selectionchange` 事件，计算 `{ startLine, endLine, selectedText }`
- 选中后在代码区高亮显示选中范围
- 底部浮出操作按钮：「AI 解读」

#### F3 · AI 解读请求

- 点击「AI 解读」→ 前端发送请求：

```json
{
  "file_name": "example.py",
  "full_content": "...(完整文件内容)",
  "selected_code": "...(选中片段)",
  "start_line": 42,
  "end_line": 58,
  "action": "explain"
}
```

- 后端 Context Engine 组装 prompt：

```
你是一个代码审查专家。以下是一个 Python 文件的完整内容，
用户选中了第 {start}-{end} 行的代码，请对选中部分进行解读。

## 完整文件
{full_content}

## 选中代码（第 {start}-{end} 行）
{selected_code}

请从以下角度分析：
1. 这段代码的功能和意图
2. 潜在问题或改进建议
3. 与上下文的关系
```

- 调用千问 API，流式返回响应
- **关键设计**：prompt 是结构化拼装的，不是对话历史追加的。每次请求独立，上下文精确可控

#### F4 · 响应展示与锚定

- 右侧面板展示 AI 响应，每条响应卡片标注 `L42-L58`
- 点击卡片上的行号标签 → 左侧代码自动滚动到对应位置并高亮
- 多次选中产生多条卡片，按时间顺序纵向排列
- 支持 Markdown 渲染（AI 响应通常包含代码块、列表）

### 1.3 技术决策与理由

| 决策 | 选择 | 理由 |
|------|------|------|
| 代码展示 | `<pre>` + highlight.js | MVP 够用，集成简单。Monaco 留到 Phase 2 |
| 状态管理 | Zustand | 轻量，比 Redux 少 80% 样板代码 |
| LLM 响应 | 流式 SSE | 用户体验好，不用干等完整响应 |
| 文件存储 | 内存 (Python dict) | MVP 不需要持久化，避免过早引入 DB |
| 样式方案 | Tailwind CSS | 快速出 UI，不纠结样式 |

### 1.4 交付标准

- [ ] 能上传 .py 文件并正确展示带语法高亮的代码
- [ ] 能选中代码段，准确检测选区行号范围
- [ ] 能调用千问 API 获取解读，流式展示在右侧面板
- [ ] 响应卡片与代码行号双向联动（点击跳转）
- [ ] 全程 localhost 运行，`make dev` 一键启动前后端

---

## Phase 2：可用工具 — 结构化 Review 流程

**目标：从"能看"进化到"能用"，形成完整的 review 工作流。**

### 2.1 代码结构树（AST）

- 后端用 Python `ast` 模块解析上传文件
- 提取：module docstring / classes / functions / imports
- 左侧新增折叠式代码树，点击节点跳转到对应代码行
- 点击模块/类/函数节点 → 右侧展示该结构的 AI 概览（自动触发）

### 2.2 Review Item 机制

- 新增交互：选中代码 → 「标记疑问」（除了「AI 解读」）
- 标记的代码段成为一个 Review Item，在代码行侧边显示标记图标
- Review Item 状态：`open` → `resolved` → `wontfix`
- 右侧面板可按 Review Item 筛选查看
- AI 回答自动挂载到对应 Review Item

### 2.3 上下文引擎增强

- 每次 AI 请求自动附带：
  - 文件级摘要（首次上传时 AI 生成一次，缓存）
  - 当前焦点代码所属函数/类的完整体
  - 同文件中已标记的 Review Items 及其 AI 回答摘要
- 这使得后续提问自带前序审查上下文，但不是无节制的对话历史

### 2.4 多文件支持

- 支持上传多个文件或一个 zip 包
- 左侧代码树变为文件树 + 结构树两级
- 跨文件引用：AI 解读时若检测到 import 依赖，自动纳入被引用文件的摘要

### 2.5 持久化（SQLite）

- 引入 SQLite，存储：
  - 上传的文件内容与 AST 结构
  - Review Items 及其状态
  - AI 响应历史
  - 文件级/模块级摘要缓存
- 页面刷新不再丢失状态
- 支持"项目"概念：一次 review session = 一个项目

### 2.6 交付标准

- [ ] 上传 .py 文件后自动生成代码结构树
- [ ] 能标记 Review Item 并管理其状态
- [ ] AI 请求自动携带结构化上下文（摘要 + 焦点 + 已有标记）
- [ ] 支持多文件上传与跨文件引用
- [ ] Review 状态持久化，刷新不丢失

---

## Phase 3：完整产品 — 多模型 + 导出 + 体验打磨

**目标：功能完整、体验专业，可以给别人用。**

### 3.1 多 LLM 支持

- 后端 LLM 层通过 adapter 模式扩展：
  - `QwenAdapter` — 通义千问（已有）
  - `DoubaoAdapter` — 字节豆包
  - `GLMAdapter` — 智谱 GLM
- 前端设置面板：选择默认模型，配置各模型 API key
- 每次请求可临时切换模型（便于对比）
- 统一的错误处理与 fallback 机制

### 3.2 代码编辑器升级

- 用 Monaco Editor 替换 `<pre>` + highlight.js
- 获得：
  - 更精确的选区管理
  - 行内装饰器（Review Item 标记直接渲染在 gutter）
  - 代码折叠
  - 搜索替换
  - minimap

### 3.3 Review 报告导出

- 一键导出当前项目的完整 Review 报告
- 格式支持：Markdown / HTML / PDF
- 报告包含：
  - 项目概览（AI 生成的项目摘要）
  - 所有 Review Items（按文件分组）
  - 每个 Item 的代码片段 + AI 分析 + 状态
  - 统计信息（总 item 数、按严重程度分布）

### 3.4 高级上下文策略

- 支持用户自定义 review 规则（如："重点关注安全问题"、"检查是否符合 PEP8"）
- 规则作为 system prompt 的一部分注入每次请求
- 项目级配置：`.coreview.json`，指定关注点、忽略文件模式等
- Token 预算管理：当文件过大时，智能截断上下文，优先保留相关部分

### 3.5 UX 打磨

- 响应式布局（面板可拖拽调整宽度）
- 键盘快捷键（`Ctrl+Shift+R` 解读选中、`Ctrl+Shift+M` 标记疑问）
- 暗色/亮色主题
- Loading 状态：流式响应时的打字机效果 + 骨架屏
- 空状态引导："上传一个文件开始 review"

### 3.6 交付标准

- [ ] 三个 LLM 均可正常调用并自由切换
- [ ] Monaco Editor 集成完成，行内标注可用
- [ ] 能导出 Markdown 格式的 review 报告
- [ ] 支持自定义 review 规则
- [ ] 键盘快捷键与主题切换可用

---

## Phase 4：开源就绪 — 工程化 + 文档 + 部署

**目标：其他开发者能 clone、能用、能贡献。**

### 4.1 工程化

- CI/CD：GitHub Actions（lint → test → build）
- 测试：
  - 后端：pytest（API 端到端测试 + context engine 单测）
  - 前端：Vitest + Testing Library（组件交互测试）
- 代码规范：ESLint + Prettier + Ruff（Python）
- Pre-commit hooks 统一卡控

### 4.2 部署方案

- Docker Compose 一键部署（前端 Nginx + 后端 Uvicorn + SQLite 卷挂载）
- 可选：部署到云上成为公开服务（加上用户认证层）
- 环境变量管理：`.env.example` 模板

### 4.3 文档

- README：项目介绍、截图/GIF、快速开始
- CONTRIBUTING.md：贡献指南
- 架构文档：Context Engine 的设计理念（这是核心卖点）
- API 文档：FastAPI 自动生成的 Swagger UI

### 4.4 开源策略

- 许可证：MIT（最大化传播）
- CHANGELOG：语义化版本 + 变更记录
- Issue / PR 模板
- 第一篇介绍文章（讲清楚"为什么结构化 UI 比对话式 review 更好"）

---

## 各 Phase 依赖关系

```
Phase 1 (MVP)
  │
  │  验证核心交互有价值
  │
  ▼
Phase 2 (可用工具)
  │
  │  形成完整工作流
  │
  ▼
Phase 3 (完整产品)
  │
  │  功能与体验到位
  │
  ▼
Phase 4 (开源就绪)
```

每个 Phase 结束时都应该是一个**可独立运行、有使用价值**的状态，而不是半成品。

---

## 当前行动：启动 Phase 1

Phase 1 的实现顺序：

```
Step 1 → 项目骨架（前后端目录、配置、开发环境一键启动）
Step 2 → F1 文件上传与代码展示
Step 3 → F2 代码选区检测
Step 4 → F3 后端 AI 解读（Context Engine + Qwen Adapter + SSE 流式）
Step 5 → F4 前端响应展示与行号锚定
Step 6 → 联调打磨，确认交付标准全部达成
```
