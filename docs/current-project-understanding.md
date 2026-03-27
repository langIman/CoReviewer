# CoReviewer 项目解构与当前理解

> 更新时间：2026-03-27
>
> 本文档基于当前仓库源码、配置与一次轻量构建验证整理而成，不以 `README.md` 为依据。后续如果代码继续演化，应以源码为准更新本文。

## 1. 项目一句话描述

CoReviewer 当前是一个面向 **Python 代码/项目的 AI 解构与审查工具**：

- 可以上传单个 `.py` 文件做选区级别的解释、审查、改写建议
- 可以上传整个 Python 项目，基于项目摘要和 import 关系做上下文增强审查
- 可以让 LLM 生成项目主流程图，并继续展开某个步骤的子流程

它的核心不是“静态分析器”，而是一个把 **代码查看器 + LLM prompt 编排 + 流式回答 + 流程图可视化** 组合起来的交互式工作台。

## 2. 当前真实技术栈

### 后端

- `FastAPI`：HTTP API 框架
- `httpx`：调用 Qwen/OpenAI 兼容接口
- `pydantic v2`：请求/响应模型
- `python-dotenv`：加载 `.env`
- 当前模型提供方：`Qwen` 兼容接口

### 前端

- `React 19` + `TypeScript`
- `Vite`
- `Zustand`：前端状态管理
- `highlight.js`：Python 代码高亮
- `react-markdown` + `remark-gfm`：渲染 AI Markdown 回复
- `@xyflow/react` + `dagre`：流程图绘制与自动布局
- `Tailwind CSS v4`：样式体系

## 3. 仓库结构的真实含义

```text
backend/
  main.py                  FastAPI 入口
  config.py                环境变量与上传限制
  models/schemas.py        API schema
  routers/
    file.py                上传与项目摘要
    review.py              流式代码审查
    visualize.py           流程图与子流程展开
  services/
    file_service.py        内存态文件/项目存储
    llm.py                 Qwen 调用封装
    import_analysis.py     import 关系解析
    symbol_resolver.py     流程节点回链源码行号
    prompts/               prompt 组装

frontend/
  src/
    App.tsx                页面总装配
    services/api.ts        前端 API 调用层
    store/useReviewStore.ts Zustand 全局状态
    components/
      UploadBar.tsx        上传/切换/可视化入口
      FileTree/            项目文件树
      CodeView/            行级代码查看与拖选
      ActionBar.tsx        explain/review/suggest 触发区
      AIPanel/             回复列表与流程图承载区
      Diagrams/            React Flow 流程图系统
    i18n/                  中英文与主题切换

TestProject/
  一个用于演示/测试上传效果的样例 Python 项目

docs/
  flow-visualization.md    历史设计说明，部分内容已过时
```

## 4. 后端架构理解

### 4.1 后端入口

`backend/main.py` 做了三件事：

1. 读取 `.env`
2. 初始化 FastAPI 和宽松的 CORS
3. 注册三个路由组：
   - `file`
   - `review`
   - `visualize`

另外暴露了一个轻量接口 `GET /api/health`，当前主要给前端显示模型名。

### 4.2 后端状态模型

当前后端没有数据库，核心状态都放在 `backend/services/file_service.py` 的模块级内存变量里：

- `_file_store`：单文件模式的已上传文件
- `_project_store`：项目模式下的所有文件内容
- `_project_name`：当前项目名
- `_project_summary`：LLM 生成的项目摘要

这意味着当前版本是明显的 MVP 形态：

- 服务重启后状态全部丢失
- 没有多用户隔离
- 没有项目历史记录
- API 的上下文依赖“最近一次上传的项目”

### 4.3 文件上传与项目摘要链路

#### `POST /api/upload`

作用：上传单个 Python 文件。

流程：

1. 读取上传内容
2. 校验扩展名和大小
3. 存入 `_file_store`
4. 返回文件内容和行数

#### `POST /api/upload-project`

作用：上传整个项目。

流程：

1. 遍历上传文件
2. 只保留 `.py`
3. 跳过不合法文件
4. 最多保留 `MAX_PROJECT_FILES`
5. 推断项目名
6. 把 `path -> content` 存入 `_project_store`
7. 返回完整文件列表给前端

#### `POST /api/project/summary`

作用：对当前已加载项目做一次全局摘要。

流程：

1. 读取当前项目文件
2. 用 `backend/services/prompts/summary.py` 组 prompt
3. 调 `call_qwen()`
4. 把摘要存入 `_project_summary`
5. 返回摘要文本

这里的摘要不是前端长期保存的数据，而是后端后续构建 review prompt 时会再次读取的“项目级上下文”。

### 4.4 代码审查链路

接口：`POST /api/review`

这是当前产品最核心的一条链路。

请求体由 `ReviewRequest` 定义，关键字段有：

- `file_name`
- `full_content`
- `selected_code`
- `start_line`
- `end_line`
- `action`
- `project_mode`

处理流程：

1. 如果是项目模式，且前端没有显式传 `related_files`
2. 后端会从 `_project_store` 中取当前文件
3. 用 `import_analysis.py` 解析 import
4. 自动补充相关文件上下文
5. 用 `prompts/review.py` 组装 prompt
6. 通过 `stream_qwen()` 调用 LLM
7. 用 `StreamingResponse` 以 SSE 形式持续把文本片段推给前端

这里有两个很关键的设计点：

- 审查是“选区驱动”的，不是整文件自动审查
- 项目模式的上下文增强，当前主要依赖 import 解析，不是完整调用图

### 4.5 流程图链路

#### 主流程图：`POST /api/visualize`

流程：

1. 读取当前项目文件
2. 用 `prompts/visualize.py` 构建严格 JSON 输出要求
3. 调 `call_qwen()`
4. 清理 markdown 包裹并解析 JSON
5. 规范化节点/边字段
6. 用 `symbol_resolver.py` 把 LLM 返回的 `symbol + code_snippet` 映射到真实源码行号
7. 返回给前端渲染

#### 子流程图：`POST /api/visualize/detail`

作用：展开某个可展开节点的内部流程。

它和主流程图的区别是：

- 输入不再是整个项目的“总览请求”
- 而是某个步骤的 `label / description / file / symbol`
- 返回同样结构的 `nodes + edges`

### 4.6 后端辅助服务各自做什么

#### `llm.py`

- `call_qwen()`：一次性返回完整文本
- `stream_qwen()`：流式返回 chunk

当前没有更高层抽象，Qwen 是直接耦合在业务里的。

#### `import_analysis.py`

作用：在项目模式下，从当前文件自动找“相关文件”。

策略比较轻量：

- AST 解析 `import` / `from ... import ...`
- 把模块名映射为项目内相对路径
- 最多带入若干文件
- 超过行数时截断

它不是全项目依赖图，只是 review 时的上下文补充。

#### `symbol_resolver.py`

作用：让流程图节点能回跳到代码行。

解析顺序：

1. `code_snippet` 精确匹配
2. `code_snippet` 去空白模糊匹配
3. AST 找调用点
4. AST 找定义点
5. 文本兜底搜索

这是一个“LLM 结果纠偏器”，是当前流程图功能里很关键的一层。

## 5. 前端架构理解

### 5.1 页面总布局

`frontend/src/App.tsx` 把页面分成三栏/两栏组合：

- 顶部：`UploadBar`
- 左侧：项目模式下显示 `FileTree`
- 中间：`CodeView + ActionBar`
- 右侧：`AIPanel`

也就是说，当前产品的核心体验是：

1. 先加载代码
2. 再选中某段代码
3. 再触发某种 AI 操作
4. 最后在右侧面板持续消费结果

### 5.2 全局状态

`useReviewStore.ts` 是前端中枢，保存：

- 当前文件
- 当前选区
- AI 回复列表
- 代码高亮行
- 当前项目及项目模式标记
- 项目摘要生成状态

几个重要行为：

- `setProject()` 会自动切换到项目模式，并默认打开第一个文件
- `clearProject()` 会把项目相关状态整体清空
- AI 回复是 append 到列表里的，不会覆盖旧结果

### 5.3 上传入口与项目模式切换

`UploadBar.tsx` 负责：

- 单文件上传
- 整个文件夹上传
- 项目清除
- 触发流程图生成
- 主题切换
- 中英文切换

项目上传完成后，前端会立即触发项目摘要生成；摘要完成前：

- `ActionBar` 的 explain/review/suggest 会被禁用
- 可视化按钮不会展示

也就是说，当前产品把“项目摘要生成成功/结束”作为项目模式下后续 AI 能力的前置条件。

### 5.4 代码查看与选区模型

`CodeView.tsx` 的几个关键点：

- 以“按行渲染表格”的方式展示代码
- 使用 `highlight.js` 做 Python 单行高亮
- 通过自定义拖拽逻辑做“按行选择”
- 单击空选区会取消选择
- 右侧 AI 卡片点击行号后，会回到中间代码区并滚动到对应位置

所以这个产品的交互基元不是 token/字符级 selection，而是“行区间”。

### 5.5 AI 操作触发

`ActionBar.tsx` 当前支持三类操作：

- `explain`
- `review`
- `suggest`

点击后会：

1. 先插入一个 loading 状态的 response
2. 调 `streamReview()`
3. 持续把 chunk 追加到对应 response
4. 流结束后标记完成

这意味着前端已经是“流式体验优先”的设计，而不是等待整段回复后再一次展示。

### 5.6 AI 结果面板

`AIPanel.tsx` + `ResponseCard.tsx` 负责展示所有 AI 输出。

普通文本类 response：

- 使用 Markdown 渲染
- 支持 GFM
- 保留代码块、表格、列表等格式

流程图类 response：

- `action === "visualize"` 时直接走 `FlowChart`
- 存储格式仍然挂在统一的 `responses` 列表里

这说明当前前端做的是“统一回复容器，按 action 决定渲染器”的架构。

## 6. 流程图系统的真实实现

这是当前项目里最有产品特征的一块。

### 6.1 数据结构

前后端围绕统一的 `FlowData` 协作：

- `nodes`
- `edges`

节点类型只有四种：

- `start`
- `end`
- `process`
- `decision`

`process` 节点还可以带：

- `file`
- `lineStart`
- `lineEnd`
- `symbol`
- `expandable`

### 6.2 渲染实现

`FlowChart.tsx` 使用：

- `ReactFlow` 负责画布和交互
- `dagre` 负责自动布局
- `CustomNode.tsx` 负责不同节点外观

当前节点语义：

- 灰色胶囊：开始/结束
- 蓝色矩形：普通步骤
- 紫色矩形：可展开步骤
- 蓝色菱形：判断节点

### 6.3 与源码联动

点击流程节点时，前端会：

1. 选中节点
2. 切换左侧文件树到该文件
3. 高亮对应源码行

这使流程图不是“纯展示图”，而是和代码区联动的导航层。

### 6.4 子流程展开

当节点 `expandable = true` 时：

- 首次点击是选中
- 再次点击会请求 `/api/visualize/detail`
- 返回的子图会被缓存到前端内存
- 左侧还有一个树形导航 `FlowTreeNav` 用于在总览/子图之间切换

所以它本质上已经形成了一个“多层流程图浏览器”。

## 7. 当前端到端数据流

### 7.1 单文件模式

1. 上传单个 `.py`
2. 前端显示代码
3. 用户拖选若干行
4. 点击 explain/review/suggest
5. 前端流式接收回复
6. 回复在右侧累积展示

### 7.2 项目模式

1. 上传整个文件夹
2. 后端只保留 `.py`
3. 前端进入项目模式并显示文件树
4. 自动请求项目摘要
5. 摘要完成后开放 review 与 visualize 能力
6. review 时后端自动补充 import 相关文件

### 7.3 可视化模式

1. 项目摘要完成
2. 用户点击“生成流程图”
3. 后端请求 LLM 输出 JSON 图
4. 后端纠正/补齐源码行号
5. 前端渲染流程图
6. 用户点击节点联动代码
7. 用户展开节点查看子流程

## 8. 当前实现的边界与约束

这些是后续改造前必须接受的“现实基线”。

### 8.1 语言范围很窄

当前只支持：

- 上传 `.py`
- Python 高亮
- Python import 解析
- Python symbol 解析

如果要支持多语言，改动会是系统级的，不是加几个 prompt 就够。

### 8.2 后端是内存态 MVP

影响：

- 不支持并发多用户
- 不支持持久化
- 当前项目上下文是“全局单例”
- 不适合部署成真正多人共享服务

### 8.3 项目理解高度依赖 LLM

尤其体现在：

- 项目摘要
- 主流程图
- 子流程图

静态分析目前只承担辅助作用，不是主引擎。

### 8.4 流程图结果是“尽量纠偏”，不是绝对准确

虽然有 `symbol_resolver`，但它仍然依赖：

- LLM 返回的 `file/symbol/code_snippet` 足够靠谱
- 代码能被 AST 解析

复杂动态调用、反射、装饰器、运行时绑定等情况，准确性会下降。

### 8.5 仓库里存在历史残留痕迹

我在源码扫描里观察到：

- `docs/flow-visualization.md` 的描述和当前代码不完全一致
- `__pycache__` 中还残留 `call_graph/context/entry_detector/analyze` 等旧模块痕迹
- 当前真实生效的后端 router 只有 `file/review/visualize`

所以以后做改造时，应该明确区分：

- “当前运行代码”
- “历史设计草稿”
- “已删除但缓存还在的旧模块”

## 9. 当前最值得作为改造切入口的模块

### 如果要提升审查质量

优先看：

- `backend/routers/review.py`
- `backend/services/prompts/review.py`
- `backend/services/import_analysis.py`

### 如果要提升项目理解能力

优先看：

- `backend/services/prompts/summary.py`
- `backend/services/prompts/visualize.py`
- `backend/services/symbol_resolver.py`

### 如果要提升交互体验

优先看：

- `frontend/src/App.tsx`
- `frontend/src/components/UploadBar.tsx`
- `frontend/src/components/CodeView/CodeView.tsx`
- `frontend/src/components/AIPanel/ResponseCard.tsx`

### 如果要强化流程图能力

优先看：

- `backend/routers/visualize.py`
- `backend/services/prompts/visualize.py`
- `frontend/src/components/Diagrams/FlowChart.tsx`
- `frontend/src/components/Diagrams/FlowTreeNav.tsx`

### 如果要把 MVP 变成可部署产品

优先看：

- `backend/services/file_service.py`
- 整个 API 的状态隔离方式
- 上传后的项目缓存/持久化方案
- 鉴权与会话模型

## 10. 我对这个项目的判断

CoReviewer 当前已经不是“一个简单的 AI 代码解释器”，而是一个正在形成中的 **Python 项目理解工作台**。它最有价值的地方在于三层能力已经接上了：

1. 代码选区级 AI 分析
2. 项目级上下文增强
3. 流程图级结构化理解

但它仍然处在非常典型的 MVP 阶段：

- 状态是内存态
- 分析主要靠 LLM
- 只覆盖 Python
- 真实架构已经快于早期文档

这反而是个好状态，因为它说明后续改造空间很大，而且当前代码规模还足够小，适合快速迭代。

## 11. 本次核验结果

为了避免本文只停留在“读代码猜测”，我额外做了两项轻量验证：

- `python -m compileall backend`：通过
- `npm run build`：通过

当前前端构建还有一个非阻塞提示：

- 打包后的主 chunk 超过 500 kB，后续如果性能优化，可以考虑按功能做代码分割

---

如果后面你要我继续推进，我建议默认把本文档当作“当前真实基线”，然后我们每做一次结构性改动，就顺手把这份文档一起更新掉。
