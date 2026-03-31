# 前端 API 接口文档

> 本文档记录前端当前使用的所有 API 接口，后端重构时以此为契约，保证前端无需改动。

---

## 数据类型定义

```typescript
// 单文件
interface FileData {
  filename: string
  content: string
  line_count: number
}

// 项目文件
interface ProjectFile {
  path: string
  content: string
  line_count: number
}

// 项目
interface ProjectData {
  project_name: string
  files: ProjectFile[]
}

// 流程图节点类型
type FlowNodeType = 'start' | 'end' | 'process' | 'decision'

// 流程图节点
interface FlowNode {
  id: string
  type: FlowNodeType
  label: string           // 中文标签
  description: string     // 一句话描述
  file?: string           // 源文件路径
  lineStart?: number      // 跳转目标起始行
  lineEnd?: number        // 跳转目标结束行
  symbol?: string         // 函数/类名，用于展开子图
  expandable?: boolean    // 是否可展开
}

// 流程图边
interface FlowEdge {
  source: string
  target: string
  label?: string          // 分支标注，如"是"/"否"
  call_line?: number      // 调用发生的行号（用于函数级图）
  call_file?: string      // 调用发生的文件（用于函数级图）
}

// 流程图数据
interface FlowData {
  nodes: FlowNode[]
  edges: FlowEdge[]
}

// AST 图分析响应
interface AnalyzeGraphResponse {
  modules: Record<string, unknown>
  definitions: Record<string, unknown>
  edges: unknown[]
  flow: {
    module_level: FlowData
    function_level: Record<string, FlowData>
  }
}

// 语义标注响应
interface AnnotateResponse {
  status: 'ok' | 'fallback'
  error?: string
  annotations: Record<string, { label: string; description: string }>
}
```

---

## API 接口列表

### 1. `POST /api/upload` — 上传单文件

**调用时机**：用户选择单个 .py 文件

**请求**：`multipart/form-data`
```
file: File
```

**响应**：`FileData`
```json
{
  "filename": "main.py",
  "content": "def main(): ...",
  "line_count": 45
}
```

---

### 2. `POST /api/upload-project` — 上传项目文件夹

**调用时机**：用户选择整个文件夹

**请求**：`multipart/form-data`
```
files: File[]   // 每个文件保留 webkitRelativePath 作为路径
```

**响应**：`ProjectData`
```json
{
  "project_name": "TestProject",
  "files": [
    { "path": "TestProject/main.py", "content": "...", "line_count": 45 },
    { "path": "TestProject/services/auth_service.py", "content": "...", "line_count": 60 }
  ]
}
```

---

### 3. `POST /api/project/summary` — 生成项目摘要

**调用时机**：上传项目成功后异步触发（不阻塞 UI）

**请求**：无 body

**响应**：
```json
{ "summary": "这是一个用户认证与待办事项管理的演示项目..." }
```

---

### 4. `POST /api/analyze/graph` — AST 调用图（纯静态，毫秒级）

**调用时机**：用户点击"可视化"按钮，Step 1，用于占位图快速展示

**请求**：无 body

**响应**：`AnalyzeGraphResponse`
```json
{
  "modules": { ... },
  "definitions": { ... },
  "edges": [ ... ],
  "flow": {
    "module_level": { "nodes": [...], "edges": [...] },
    "function_level": {
      "TestProject/main.py": { "nodes": [...], "edges": [...] }
    }
  }
}
```

**前端用途**：取 `flow.module_level` 作为骨架图先行展示，等待 overview 结果替换。

---

### 5. `POST /api/analyze/overview` — 语义化总览流程图（LLM）

**调用时机**：用户点击"可视化"按钮，Step 2，替换骨架图

**请求**：无 body

**响应**：`FlowData`
```json
{
  "nodes": [
    { "id": "1", "type": "start", "label": "开始", "description": "程序入口" },
    {
      "id": "2",
      "type": "process",
      "label": "注册用户 Alice 和 Bob",
      "description": "调用 auth.register 两次创建用户",
      "file": "TestProject/main.py",
      "symbol": "register",
      "lineStart": 11,
      "lineEnd": 12,
      "expandable": true
    },
    { "id": "3", "type": "decision", "label": "登录是否成功?", "description": "检查 token" },
    { "id": "4", "type": "end", "label": "结束", "description": "程序完成" }
  ],
  "edges": [
    { "source": "1", "target": "2", "label": "" },
    { "source": "2", "target": "3", "label": "" },
    { "source": "3", "target": "4", "label": "是" },
    { "source": "3", "target": "5", "label": "否" }
  ]
}
```

---

### 6. `POST /api/analyze/detail` — 展开函数内部逻辑（LLM）

**调用时机**：用户双击可展开（紫色）节点

**请求**：
```json
{ "qualified_name": "TestProject/services/auth_service.py::AuthService.register" }
```

**响应**：`FlowData`（格式同 overview，描述该函数内部执行步骤）

---

### 7. `POST /api/analyze/annotate` — LLM 语义标注（按需）

**调用时机**：当前未被主流程调用，预留接口

**请求**：
```json
{ "modules": ["TestProject/services/auth_service.py"] }  // 可选，不传则标注全部
```

**响应**：`AnnotateResponse`
```json
{
  "status": "ok",
  "annotations": {
    "TestProject/services/auth_service.py::AuthService.register": {
      "label": "注册用户",
      "description": "验证邮箱和密码格式，创建用户并存储"
    }
  }
}
```

---

### 8. `POST /api/review` — 流式代码审查

**调用时机**：用户选中代码后点击"解释"/"审查"/"建议"

**请求**：
```json
{
  "file_name": "main.py",
  "full_content": "完整文件内容...",
  "selected_code": "auth.register(...)",
  "start_line": 11,
  "end_line": 12,
  "action": "explain",
  "project_mode": true
}
```

**响应**：SSE 流
```
data: "这段代码"
data: "调用了注册函数..."
data: [DONE]
```

---

## 可视化完整触发流程

```
用户点击"可视化"
  │
  ├─ [并行] POST /api/analyze/graph
  │     └─ 立即展示模块级骨架图（毫秒级）
  │
  └─ [等待] POST /api/analyze/overview
        └─ LLM 返回后替换骨架图为语义流程图

用户双击紫色节点（如"注册用户"）
  │
  ├─ 命中缓存 → 直接切换
  └─ 未命中 → POST /api/analyze/detail
               └─ LLM 返回子流程图，缓存后展示
```

---

## 节点点击跳转逻辑

```
单击节点
  │
  ├─ 节点有入边且入边含 call_line → 跳到 call_file:call_line（调用位置）
  └─ 无入边（入口节点） → 跳到 file:lineStart（定义位置，fallback）
```

---

## 错误响应格式（所有接口统一）

```json
{ "detail": "错误描述信息" }
```

非致命错误（`analyzeGraph` 失败、`analyzeDetail` 失败）前端静默处理，不打断用户流程。
