# 项目解构算法优化计划

> 核心思路：**静态分析构建骨架 + LLM 语义增强**，替代当前"全量代码 → LLM 一次性生成"的方案

---

## 现状问题

当前解构流程：

```
全部源码 → 拼入 Prompt → LLM 一次性返回流程图 JSON → symbol_resolver 猜行号
```

| 问题        | 影响                                                    |
| --------- | ----------------------------------------------------- |
| Token 限制  | 大项目放不进 Prompt，文件被截断到 150 行                            |
| 结构靠 LLM 猜 | 调用关系可能产生幻觉，结果不可复现                                     |
| 行号不可靠     | LLM 返回的 symbol/code_snippet 需要 4 级 fallback 去猜，仍有失败可能 |
| 全量调用      | 每次生成或展开子图都要完整调用 LLM，成本高、延迟大                           |

## 目标架构

```
源码 → AST 静态分析（确定性骨架）→ LLM（语义标注 + 步骤合并）→ 可交互流程图
```

分为 **4 个阶段**，可逐步实施，每个阶段独立可用。

---

## Phase 1：AST 调用图提取

> 用 AST 替代 LLM 生成结构骨架，解决行号准确性和结构可靠性

### 1.1 函数/类定义收集

遍历项目所有 [.py](file:///root/miniconda3/CoReviewer/backend/main.py) 文件，提取：

```python
@dataclass
class SymbolDef:
    qualified_name: str   # "backend/routers/file.py::upload_file"
    name: str             # "upload_file"
    kind: str             # "function" | "class" | "method"
    file: str             # "backend/routers/file.py"
    line_start: int
    line_end: int
    decorators: list[str] # ["@router.post('/api/upload')"]
    docstring: str | None
    params: list[str]     # ["file: UploadFile"]
```

**实现要点**：

- 用 `ast.parse()` → `ast.walk()` 遍历 `FunctionDef` / `AsyncFunctionDef` / `ClassDef`
- 对 class 内的方法用 `ClassName.method_name` 做 qualified_name
- 提取装饰器文本用于后续入口识别

### 1.2 调用关系提取

对每个函数体内，分析调用了哪些函数：

```python
@dataclass
class CallEdge:
    caller: str       # qualified_name of caller
    callee: str       # function name being called
    file: str         # caller's file
    line: int         # call site line number
    call_type: str    # "direct" | "attribute" (xxx.foo())
```

**实现要点**：

- 遍历函数体内的 `ast.Call` 节点
- `ast.Name` → 直接调用 (`foo()`)
- `ast.Attribute` → 属性调用 (`self.foo()`, `service.bar()`)
- 结合 import 分析，将 callee 名称**解析到项目内的具体函数**（复用 [import_analysis.py](file:///root/miniconda3/CoReviewer/backend/services/import_analysis.py) 的逻辑）

### 1.3 调用图解析

```python
def build_call_graph(project_files: dict[str, str]) -> CallGraph:
    """
    返回:
      - definitions: dict[str, SymbolDef]  所有定义
      - edges: list[CallEdge]              调用关系
      - entry_points: list[SymbolDef]      入口点
    """
```

**入口点自动检测规则**：

1. `@app.get/post/put/delete` 或 `@router.xxx` 装饰 → API endpoint
2. `if __name__ == "__main__"` 块 → 脚本入口
3. `@click.command` / `@app.command` → CLI 入口
4. 没有被任何其他函数调用的顶层函数 → 潜在入口

### 新增文件

```
backend/services/
├── call_graph.py          # SymbolDef, CallEdge, build_call_graph()
├── entry_detector.py      # detect_entry_points()
└── import_analysis.py     # 现有，小幅扩展
```

### 产出

Phase 1 完成后可以独立输出**原始调用图**给前端渲染——即使不调用 LLM，用户也能看到项目结构。

---

## Phase 2：LLM 语义增强

> LLM 不再生成结构，只做"标注 + 合并建议"

### 2.1 Prompt 重新设计

**输入给 LLM 的内容**（大幅减少 Token）：

```
项目调用图骨架：
- upload_file (routers/file.py:18-30) → validate_file, store_file
- review_code (routers/review.py:16-42) → get_related_files, build_review_prompt, stream_qwen

每个函数的签名和 docstring：
- validate_file(filename, content) -> str | None: "验证上传文件"
- store_file(filename, content) -> None: "存储文件到内存"
...

请为以上调用链生成：
1. 每个节点的中文 label（简洁）和 description（一句话）
2. 哪些连续调用可以合并为一个逻辑步骤（如 validate + store → "文件上传处理"）
3. 哪些节点是条件分支（decision）
```

**输出 JSON 格式不变**，但 nodes 的 [file](file:///root/miniconda3/CoReviewer/Makefile) / `lineStart` / `lineEnd` 由 AST 直接填充，不需要 LLM 提供。

### 2.2 降级策略

```
LLM 标注成功 → 展示语义化流程图
LLM 标注失败 → 展示原始调用图（函数名作为 label）
LLM 部分失败 → 成功标注的节点展示语义名，失败的用函数名
```

### 2.3 Token 优化

| 策略           | 说明                                 |
| ------------ | ---------------------------------- |
| **只发签名不发全文** | 函数体不发给 LLM，只发签名 + docstring + 调用关系 |
| **分批标注**     | 大项目拆分为模块级 batch，每个 batch 独立标注      |
| **缓存**       | 相同函数签名 + 相同调用关系 → 缓存 LLM 标注结果      |

---

## Phase 3：分层渐进式解构

> 三层结构按需展开，只在第 3 层调用 LLM

```
第 1 层（模块级）：每个 .py 文件是一个节点，边 = import 关系
                   ← 纯 AST，零 LLM 调用

第 2 层（函数级）：文件内的函数/类定义 + 调用关系
                   ← 纯 AST + 可选 LLM 标注

第 3 层（逻辑级）：函数内部的执行步骤、条件分支、循环
                   ← 需要 LLM 分析函数体
```

### 用户交互流程

```
1. 上传项目 → 立即展示模块级全景图（毫秒级，无需等 LLM）
2. 点击某模块 → 展开到函数级调用图（毫秒级）
3. 同时后台异步请求 LLM 标注 → 标注完成后平滑替换 label
4. 点击某函数 → 如需展开内部逻辑，调用 LLM 分析该函数体
```

### 前端改造

- [FlowChart](file:///root/miniconda3/CoReviewer/frontend/src/components/Diagrams/FlowChart.tsx#25-32) 增加**层级切换**（模块 / 函数 / 逻辑）
- 模块级和函数级图可以在毫秒内渲染（骨架先行）
- LLM 标注结果异步到达后做**动画过渡**更新 label

### 新增 API

```
POST /api/analyze/graph         → 返回模块级 + 函数级调用图（纯 AST）
POST /api/analyze/annotate      → LLM 标注请求（异步）
POST /api/analyze/detail/{func} → 展开某函数内部逻辑（LLM）
```

---

## Phase 4：增强分析能力

> 在调用图基础上叠加更多静态分析

### 4.1 数据流追踪

```python
# 追踪变量从创建到使用的流向
def trace_data_flow(func_node: ast.FunctionDef) -> list[DataFlowEdge]:
    """
    识别：参数 → 局部变量 → 返回值 → 被谁消费
    """
```

在流程图节点上标注"数据从哪来、到哪去"。

### 4.2 复杂度标注

```python
def compute_complexity(func_node: ast.FunctionDef) -> int:
    """圈复杂度（Cyclomatic Complexity）"""
    # 统计 if/elif/for/while/try/except/and/or 数量
```

在节点上用颜色深浅或徽标展示复杂度，帮用户定位"最复杂的函数在哪"。

### 4.3 依赖热力图

统计每个模块被 import 的次数，生成热力图标注在模块级流程图上，高频依赖模块 = 核心模块。

---

## 实施优先级

| 顺序  | 阶段                | 预估工作量 | 核心收益                      |
|:---:|:-----------------:|:-----:| ------------------------- |
| ①   | Phase 1 - AST 调用图 | 2-3 天 | 结构 100% 准确，行号精确，消除 LLM 幻觉 |
| ②   | Phase 3 - 分层展示    | 1-2 天 | 首次渲染零延迟，大幅减少 LLM 调用       |
| ③   | Phase 2 - LLM 标注  | 1-2 天 | 语义化标注，Prompt Token 大幅减少   |
| ④   | Phase 4 - 增强分析    | 持续迭代  | 差异化功能，提升产品深度              |

> **建议从 Phase 1 开始**，完成后项目的核心竞争力会从"LLM 套壳"变成"静态分析 + LLM 增强"的混合智能。
