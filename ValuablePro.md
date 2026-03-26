# CoReviewer 有价值的问题与解决方案记录

## 1. 流程图节点代码行号跳转不准确

### 问题描述

流程图中每个模块（节点）关联了 `file` 和 `line` 字段，用户点击节点后会跳转到对应代码行。
但由于行号是由 LLM 直接生成的，LLM 对代码的理解是语义层面的而非逐行计数，因此行号经常不准确，导致跳转到错误的位置。

### 问题分析

1. **LLM 天生不擅长数行号** — 它擅长理解"这段逻辑对应哪个函数"，但不擅长精确计算某个函数在第几行
2. **跳转目标应是调用点而非定义点** — 流程图展示的是执行流，节点对应的是函数被调用的位置（如 `main.py` 中的 `authenticate_user(...)`），而非函数定义的位置（如 `auth_service.py` 中的 `def authenticate_user`）
3. **同一函数可能被多次调用** — 仅靠函数名无法区分同一文件中的多次调用

### 最终方案：LLM 返回 symbol + code_snippet，后端 AST 解析真实行号

**核心思路：发挥各自长处** — LLM 负责语义识别（哪个函数、哪段代码），行号计算交给代码精确完成。

#### Prompt 改造

让 LLM 返回 `symbol`（函数/类名）和 `code_snippet`（调用点附近的一小段代码）代替原来的 `line` 字段：

```json
{
  "id": "3",
  "type": "process",
  "label": "管理员认证",
  "file": "main.py",
  "symbol": "authenticate_user",
  "code_snippet": "result1 = authenticate_user(admin_name, pwd)"
}
```

#### 后端行号解析（四级 fallback）

1. **code_snippet 精确匹配** — 在目标文件中搜索这段文本，找到则直接返回行号（最准确）
2. **code_snippet 模糊匹配** — 去掉空格后比对，容忍 LLM 的轻微格式差异
3. **symbol 调用点匹配** — 用 AST 找目标文件中所有该函数的 `ast.Call` 调用，取第一个
4. **symbol 定义匹配** — 最终兜底，找 `ast.FunctionDef` / `ast.ClassDef` 的定义位置

#### 前端改进

节点携带解析后的 `lineStart` / `lineEnd`，点击后高亮整个相关代码区域而非单行。
