# 流程图生成全流程

## 一、用户操作

用户上传项目 → 等待摘要生成完成 → 点击顶栏紫色按钮 **"生成流程图"**

---

## 二、前端触发

**文件：** `UploadBar.tsx` → `handleVisualize()`

```
1. 在右侧面板创建一个空的 ResponseCard（action="visualize", loading=true）
2. 调用 API：POST /api/visualize
3. 等待响应（非流式，一次性返回完整 JSON）
4. 将 JSON stringify 后存入 response.content
5. 标记 loading=false
```

---

## 三、后端处理

### 3.1 端点接收请求

**文件：** `backend/routers/review.py` → `visualize_project()`

```python
POST /api/visualize
  → 从内存获取 _project_store（所有 .py 文件内容）
  → 调用 build_visualize_prompt() 构建 prompt
  → 调用 call_qwen()（非流式，等待完整响应）
  → 清理 markdown 包裹（如 ```json ... ```）
  → JSON.parse 校验结构
  → 返回 { nodes: [...], edges: [...] }
```

### 3.2 Prompt 构建

**文件：** `backend/services/context.py` → `build_visualize_prompt()`

将所有项目文件拼成这样的 prompt：

```
System: "你是代码架构分析专家。只返回 JSON，不要其他内容。"

User:
  "分析以下 Python 项目，从 main() 入口开始追踪调用链路。

  ### main.py
  ```python
  （文件内容）
  ```
  ### services/auth_service.py
  ```python
  （文件内容）
  ```
  ...

  请返回如下 JSON：
  {
    nodes: [{ id, label, file, line, description }],
    edges: [{ source, target, order, label }]
  }

  要求：
  - 从入口开始按执行顺序追踪
  - 节点控制在 20 个以内
  - order 按执行顺序递增
  - description 用中文"
```

### 3.3 LLM 调用

**文件：** `backend/services/llm.py` → `call_qwen()`

```
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
  model: qwen-plus（由 .env 配置）
  stream: false（非流式，等完整响应）
  timeout: 120s
```

### 3.4 LLM 返回示例

```json
{
  "nodes": [
    { "id": "1",  "label": "main()",                    "file": "TestProject/main.py",                    "line": 9,  "description": "程序入口，初始化服务" },
    { "id": "2",  "label": "AuthService.register()",    "file": "TestProject/services/auth_service.py",   "line": 13, "description": "注册新用户" },
    { "id": "3",  "label": "User.create()",             "file": "TestProject/models/user.py",             "line": 13, "description": "创建用户实例" },
    { "id": "4",  "label": "validate_email()",          "file": "TestProject/utils/validators.py",        "line": 5,  "description": "校验邮箱格式" },
    { "id": "5",  "label": "validate_password()",       "file": "TestProject/utils/validators.py",        "line": 10, "description": "校验密码强度" },
    { "id": "6",  "label": "AuthService.login()",       "file": "TestProject/services/auth_service.py",   "line": 28, "description": "用户登录" },
    { "id": "7",  "label": "User.check_password()",     "file": "TestProject/models/user.py",             "line": 25, "description": "校验密码哈希" },
    { "id": "8",  "label": "TodoService.add_todo()",    "file": "TestProject/services/todo_service.py",   "line": 10, "description": "添加待办事项" },
    { "id": "9",  "label": "TodoService.get_todos()",   "file": "TestProject/services/todo_service.py",   "line": 20, "description": "获取待办列表" },
    { "id": "10", "label": "TodoService.complete_todo()","file": "TestProject/services/todo_service.py",   "line": 27, "description": "完成待办事项" }
  ],
  "edges": [
    { "source": "1",  "target": "2",  "order": 1,  "label": "注册用户 alice" },
    { "source": "2",  "target": "3",  "order": 2,  "label": "调用 User.create" },
    { "source": "3",  "target": "4",  "order": 3,  "label": "校验邮箱" },
    { "source": "3",  "target": "5",  "order": 4,  "label": "校验密码" },
    { "source": "1",  "target": "6",  "order": 5,  "label": "用户登录" },
    { "source": "6",  "target": "7",  "order": 6,  "label": "校验密码哈希" },
    { "source": "1",  "target": "8",  "order": 7,  "label": "添加待办" },
    { "source": "1",  "target": "9",  "order": 8,  "label": "获取待办列表" },
    { "source": "1",  "target": "10", "order": 9,  "label": "完成一个任务" }
  ]
}
```

---

## 四、前端渲染

### 4.1 数据流

```
ResponseCard 检测到 action="visualize"
  → JSON.parse(content)
  → 传给 <FlowChart data={flowData} />
```

### 4.2 布局计算（一次性）

**文件：** `FlowChart.tsx` → `computeLayout()`

```
data.nodes + data.edges
  → dagre.graphlib.Graph
  → 设置方向：从上到下（TB）
  → 设置节点间距：nodesep=30, ranksep=70
  → dagre.layout(g)
  → 输出每个节点的 { x, y } 坐标
```

### 4.3 React Flow 渲染

```
节点 → 自定义 CustomNode 组件
  ┌─────────────────────┐
  │ TestProject/main.py  │  ← 文件名（灰色小字）
  │ main()               │  ← 函数名（粗体）
  │ Line 9               │  ← 行号
  └─────────────────────┘

边 → 带箭头连线 + label 文字
```

### 4.4 动画序列

```
t=0ms       所有节点灰色半透明，所有边灰色
t=400ms     入口节点 main() 点亮（灰→蓝，放大 105%）
t=1000ms    edge order=1 → 点亮 AuthService.register()，对应边变蓝色流动虚线
t=1600ms    edge order=2 → 点亮 User.create()
t=2200ms    edge order=3 → 点亮 validate_email()
t=2800ms    edge order=4 → 点亮 validate_password()
...
t=最后      所有节点亮起，显示"重播动画"按钮
```

动画实现：
- `useNodesState` / `useEdgesState` 管理节点和边的状态
- `setTimeout` 按 order 逐步调用 `lightUpNode()` 和 `lightUpEdge()`
- 节点通过 CSS `transition-all duration-500` 实现平滑过渡
- 边通过 React Flow 的 `animated: true` 属性显示流动粒子

### 4.5 交互

| 操作 | 效果 |
|------|------|
| 鼠标滚轮 | 缩放 |
| 鼠标拖拽空白区 | 平移画布 |
| 点击节点 | 左侧切换到对应文件，高亮对应行 |
| hover 节点 | 显示 description（tooltip） |
| 点击"重播动画" | 重置所有状态，重新播放 |
| 左下角 +/- 按钮 | 缩放控制 |
| 左下角方框按钮 | fit view（适应画布） |

---

## 五、完整时序图

```
用户                    前端                      后端                     LLM (通义千问)
 │                       │                         │                         │
 │  点击"生成流程图"      │                         │                         │
 │──────────────────────→│                         │                         │
 │                       │  创建 loading card       │                         │
 │                       │  POST /api/visualize    │                         │
 │                       │────────────────────────→│                         │
 │                       │                         │  拼接所有文件内容         │
 │                       │                         │  构建 prompt             │
 │                       │                         │  POST chat/completions  │
 │                       │                         │────────────────────────→│
 │                       │                         │                         │  分析代码
 │                       │                         │                         │  生成 JSON
 │                       │                         │←────────────────────────│
 │                       │                         │  校验 JSON              │
 │                       │  { nodes, edges }       │                         │
 │                       │←────────────────────────│                         │
 │                       │  JSON.stringify → store  │                         │
 │                       │  ResponseCard 渲染       │                         │
 │                       │  dagre 计算布局          │                         │
 │                       │  React Flow 渲染节点     │                         │
 │                       │  启动逐步动画            │                         │
 │  看到动画流程图        │                         │                         │
 │←──────────────────────│                         │                         │
```

---

## 六、涉及的文件

| 文件 | 职责 |
|------|------|
| `frontend/src/components/UploadBar.tsx` | 触发按钮 + 调用 API |
| `frontend/src/services/api.ts` | `visualizeProject()` HTTP 请求 |
| `frontend/src/components/AIPanel/ResponseCard.tsx` | 检测 action="visualize"，渲染 FlowChart |
| `frontend/src/components/AIPanel/FlowChart.tsx` | 核心：dagre 布局 + React Flow 渲染 + 逐步动画 |
| `frontend/src/types/index.ts` | FlowNode, FlowEdge, FlowData 类型定义 |
| `backend/routers/review.py` | `POST /api/visualize` 端点 |
| `backend/services/context.py` | `build_visualize_prompt()` prompt 构建 |
| `backend/services/llm.py` | `call_qwen()` 非流式 LLM 调用 |
