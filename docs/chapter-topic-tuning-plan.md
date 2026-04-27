# 核心架构页 + 专题深入页 Prompt 调优计划

本计划是 [prompt-tuning-playbook.md](./prompt-tuning-playbook.md) 在 chapter / topic 两类页面上的具体落地。
playbook 是方法论，本文件是排期 + 决策记录。

**当前进度**：
- ✅ 模块页 iter4 收官（single-shot 顶点）
- ✅ Chapter 页迭代完成（12 步自查清单 + 教科书概念黑名单 + 双步设计洞察审计）
- ⏳ Topic 页本轮启动

---

## 一、Chapter 页（已完成 · 经验沉淀）

### 收官的关键约束（topic 直接复用候选）
- **12 步自查清单**：跨模块跳转 ≥ 3 / refs ≥ N / H2 ≥ 4 / mermaid ≥ 1 / 表格 ≥ 1 / 引用块 3-6 / 每 H2 导语段 / 黑名单短语自查 / 设计洞察"两步审"
- **教科书概念黑名单**：「唯一索引 / DuplicateKeyException / 幂等键 / 对账任务 / 死信队列 / 定时补偿 / 状态机 / 金融级 / Saga / 分布式事务 / 两阶段提交」——出现前必须先在源码 grep 命中
- **设计洞察"两步审"**：每条必须带 `#code:ref_X` 锚点 + 不能搬到其他章节（即聚焦本章主题）
- **关键文件源码塞 prompt** 是抓 v1-v4 演进轨迹的根因——AST skeleton 漏注释代码块和 inner class

这些都需要按 topic 特性**有选择**地迁移，不是无脑抄。

---

## 二、Topic 页：当前差距诊断

| 维度 | chapter iter4 | topic 当前 baseline |
|---|---|---|
| Prompt 篇幅 | ~250 行 | ~30 行 |
| 信息源 | 模块清单 + 跨模块依赖 + skeleton 索引 + 关键文件**完整源码** + 运行线索 | 模块清单 + 跨模块依赖（**0 行源码**） |
| 视觉/密度约束 | H2 ≥ 4、mermaid/表格/引用块硬要求 | 无 |
| 反退化清单 | 6+ 条 + 黑名单 | 无 |
| 自查清单 | 12 步 | 无 |

**最严重的是信息源**——topic 比 chapter baseline 还薄。playbook §一 已点名：topic 是**最聚焦**的页面，但目前给的输入反而最少，0 行源码进 prompt，LLM 只能凭模块描述硬编"教科书秒杀"。**这是结构性缺陷，调 prompt 救不了**。

---

## 三、四阶段路线（topic）

### 阶段 0：基础设施

1. **`test/scripts/preview_topic_page.py`** — 镜像 [`preview_chapter_page.py`](../test/scripts/preview_chapter_page.py)；复用 split / outline 缓存；新增 `topic_page_llm_*.json` 缓存（按 prompt+model 哈希），prompt 改动自动失效，`--refresh-page` 强制重跑
2. **`test/scripts/dump_topic_prompt.py`** — dump 真实 step1 / step2 prompt，校验输入未脱钩（playbook §一 死参数隐患）
3. **手写 Topic Gold**（最重要，不能跳过）：
   - **选题：多层防御策略（Lua + Redisson + SQL stock>0）** — playbook §四 推荐：非显然设计 + 可对比的替代方案 + 能逼出"为什么"
   - 整篇都是「为什么这样而不是别的」——犀利、聚焦、有立场
   - 必含：替代方案对比表（至少 2 个替代）+ 失败模式表（每层防什么具体失败）+ 设计洞察散布到各 H3

### 阶段 1：两步管线改造（结构性修复信息源）

playbook §六 已决策走方案 B。代价：每个 topic 页多 1 次 LLM 调用 / ~50s 延迟，换取质量从 30%（凭模块摘要硬编）→ 70-80% Gold。

**Step 1（侦察）·新增**

```
build_topic_recon_prompt:
  input  = topic_title + topic_brief + modules_text + module_skeletons_text
           （每模块 top-6 核心符号，含装饰器/参数/in-out 度数/L 行号）
  output = JSON: {relevant_symbols: [{module_idx, symbol_qname, reason}, ...]}
           粒度：函数/方法级（不是类级，topic 聚焦设计点）
           数量：3-8 条
  调用：call_qwen + 极简 prompt（< 80 行），thinking=off
  缓存：(topic_title + topic_brief + modules_fingerprint) →
        SPLIT_CACHE_DIR/topic_recon_<key>.json
```

**Step 2（写作）·改造现有**

```
新增 _fmt_focused_symbols_source(relevant_symbols, ast_model, project_files):
  - 按 step1 选中符号定位 file + line_start/line_end
  - 抽 ±N 行上下文（默认每符号 80 行预算，总预算 12000 字符）
  - 不像 chapter 按文件给完整源码——topic 要符号级聚焦
  - 输出格式：### {file_path} :: {symbol_name} (L{start}-L{end})\n```\n{snippet}\n```

build_topic_page_prompt 改造：
  - 新增参数 relevant_symbols_text（成为主输入，原 modules_text/module_deps_text 下放为"上下文"）
  - 新增 min_code_refs=3 硬约束
  - 增视觉/反退化/自查约束（见阶段 2）
```

**SOP**：每加一条新输入，跑 dump_topic_prompt.py 搜值是否真进 prompt——避免 `target_length_hint` 死参数。

**Step1 thinking 决策**：默认关闭。若首轮发现 step1 漏掉关键符号或选了无关符号再切到 thinking on（成本 +30s）。

### 阶段 2：六技巧迁移（topic 版）

| 技巧 | chapter 做法 | **topic 做法** |
|---|---|---|
| 视觉层次主力 | mermaid + 引用块 | **反问式 H3 + 对比表**（每个 H3 标题就是一个反问，例 `### 为什么不是 BlockingQueue？`） |
| 概览节奏 | 每 H2 2-4 句导语 | **开篇必填「问题陈述」段**——这个设计点要解决哪个具体痛点；每个反问 H3 给小问题 |
| 设计洞察 | 5-8 条**收尾** | **整篇都是洞察**——分散到每个 H3 末尾，不再集中收尾 |
| 演进轨迹 | 注释代码作开篇 | 该专题的设计演进（v1 → v现役）写在「问题陈述」之后 |
| 自查清单硬指标 | refs ≥ N / 表 ≥ 1 / H2 ≥ 4 | **替代方案对比 ≥ 2 / 失败模式 ≥ 2 /「为什么」型分析 ≥ 5 / `#code:ref_N` ≥ 3** |
| 反退化 | 教科书化 / 平行罗列模块 | **水文化 / 教科书分布式锁科普 / 「是什么」段落 / 凭脑补编 step1 之外的符号** |

**直接复用 chapter 收官经验**：
- 教科书概念黑名单整段搬过来——topic 高发幻觉点和 chapter 重叠
- 设计洞察"两步审"约束（必须有 `#code:ref_X` 锚点 + 必须聚焦本专题）——散布到各 H3 末尾后这个约束更要紧
- `#code` 锚点必须出现在 step1 选中符号清单内（同构于 chapter "必须在 skeleton 里"约束），杜绝凭空编符号

### 阶段 3：迭代节奏（每轮 2-3 改动）

| 轮次 | 改动重点 |
|---|---|
| iter1 | 两步管线打通 + 信息源到位 + 视觉骨架（反问 H3、对比表、问题陈述段） |
| iter2 | 概览节奏 + 整篇为什么化（散布洞察） |
| iter3 | 反退化清单（**先看 iter1/2 真实失败模式再加**，避免照抄 chapter 反成 prompt 臃肿） |
| iter4 | 自查清单收尾（替代方案数 / 失败模式数 / 为什么型洞察数 / refs 数） |

每轮跑 baseline → diff Gold → 统计指标变化（playbook §四 第二步对比表）。

### 阶段 4：何时停
- 一轮迭代的边际收益明显下降
- 剩下差距是模型能力天花板（playbook §五 隐式假设挖掘 / 写后元认知 / 跨段落连接观察）
- 承认天花板优于过度优化

---

## 四、决策记录

| 决策 | 选项 | 理由 |
|---|---|---|
| 计划保存形式 | 独立 markdown 与 playbook 并列 | playbook 方法论 / 本文件项目排期 |
| Topic 源码输入策略 | **方案 B（两步小管线）** | A 启发式漏检风险高；topic 本来就最依赖"先识别再写"思维 |
| Chapter Gold 选题（已交付） | 秒杀订单端到端流程 | 横跨多模块、有真实叙事价值 |
| **Topic Gold 选题** | **topic 1「Redis 分布式锁的演进权衡」**（与 outline 实际产出对齐） | 原计划"多层防御策略"未被 outliner 选中；topic 1 的 v1→v4 演进材料几乎等价（lock 是三层防御的中间层），Gold 在 lock 视角下编排，期间引出多层防御作为上下文 |
| **Step1 thinking** | **关闭（默认）** | 侦察任务结构化，thinking off 已够；按需切换 |
| **Step1 选符号粒度** | **函数/方法级** | topic 聚焦设计点，函数级最贴；按 line_start/line_end ±N 行抽源码片段 |
| 开工顺序 | Chapter 先 → Topic 后 | Chapter 信息源缺口小、改造直接；Topic 需先验证两步管线工程量 |

---

## 五、追踪表

### 阶段 0：基础设施
- [x] `preview_chapter_page.py` + outline 缓存
- [x] `preview_topic_page.py`
- [x] `dump_chapter_prompt.py`
- [x] `dump_topic_prompt.py`
- [x] Chapter Gold 手写完成
- [x] Topic Gold 手写完成（[topic_1_gold.md](../test/gold/topic_1_gold.md) — Redis 分布式锁的演进权衡，~2400 字）

**阶段 0 验证结果（2026-04-26）**：
- baseline prompt dump 大小：system 146 / user 2960 chars，**0 行源码**（仅模块清单 + 跨模块依赖）
- 印证了「信息源结构性缺陷」诊断 —— 阶段 1 两步管线必须先做，prompt 调优才有意义

### 阶段 1：Chapter 信息源（已完成）
- [x] 关键文件完整源码塞 prompt（抓注释代码 / inner class）
- [x] 模块核心符号 skeleton（参数 + 装饰器 + 度数 + 行号）
- [x] 跨模块调用频次 + 运行线索

### 阶段 1：Topic 两步管线（已完成 2026-04-26）
- [x] `build_topic_recon_prompt` 实现（极简，输入仅符号目录 + 模块清单）
- [x] step1 自动按 prompt 哈希缓存（preview 脚本里的 `cached_call_qwen` 透明覆盖）
- [x] `_fmt_focused_symbols_source`（符号级 ±20 行片段，>50% 文件覆盖时给全文）
- [x] `_fmt_symbol_catalog_for_recon`（行首带 qualified_name 的 step1 候选库）
- [x] `_fmt_relevant_symbols`（step1 输出 → step2 清单展示）
- [x] `generate_topic_page` 改造为两步（含 `_topic_recon` 内部函数）
- [x] `build_topic_page_prompt` 接 `relevant_symbols_text` + `focused_source_text` + `min_code_refs=3`
- [x] 跑 dump_topic_prompt.py 校验：step1 7327 chars / step2 13891 chars（含 12000 字符预算的源码）
- [x] 跑 preview_topic_page.py 端到端：3278 chars 输出，含问题陈述/演进表/反问 H3/对比表/4 条洞察

### 阶段 2-3：Chapter prompt 迭代
- [x] iter1 / iter2 / iter3（已收官 · 见 [chapter_3_gap_analysis.md](../test/gold/chapter_3_gap_analysis.md)）

### 阶段 2-3：Topic prompt 迭代（已收官 2026-04-26）

| 迭代 | 字数 | 演进代际数 | 反问 H3 数 | 洞察 | code refs | 关键改进 |
|---|---|---|---|---|---|---|
| Baseline | ~2000 | 0 | 0 | 0 | 0 | 0 行源码进 prompt |
| **iter1** | 3278 | 3（错） | 2 | 4 | 6 | 两步管线 + 视觉骨架 |
| **iter2** | 3583 | 3（错） | 3 | 4 | 5 | ⚑ 注释信号 + 跨主题禁条 + 概览节奏 + 项目语料 |
| **iter3** | 3910 | 3（对）| 4 | 5 | 5 | 演进维度区分 + 反退化清单 + 教科书黑名单 |
| **iter4** | 3855 | **5（对）**| 4 | 4 | 5 | 11 项自查清单（黑名单回查 + 编造数字回查） |

iter4 = 当前 single-shot 顶点：
- ✅ 演进表完全对齐 Gold（synchronized → SimpleRedisLock → Redisson+DB → BlockingQueue → Lua+Stream+SQL CAS）
- ✅ 抓到 Gold 核心反问"为什么 Lua 已经判过重复，Java 还要再 query DB？"
- ✅ 自查抓出 iter3 的"金融/交易"黑名单词 + "锁租期 1/3 检查"编造数字，全部清理掉
- ✅ Output: [/tmp/topic_1_iter4.md](file:///tmp/topic_1_iter4.md)

### 剩余差距（Playbook §五 模型能力天花板）

iter4 vs Gold 仍缺：
- **隐式假设挖掘**：`Collections.emptyList()` 暗示放弃 Redis Cluster——这种"代码细节里读出架构限制"
  的洞察 single-shot LLM 很难自发抓到（playbook §五 已点名）
- **写后元认知**：Gold 末尾"承诺单"、"`tryLock()` 不带超时是有意的"这类需要写后回看才能产生的洞察
- **跨段落连接观察**：`intern()` 的元空间泄漏 vs 集群失效是两个独立问题——iter3 抓到了一次但 iter4 自查时被"黑名单"误删

这些都需要 ReAct 架构（多步观察-推理）才能突破，**不是 prompt 调优能解决的**。
承认天花板优于硬撑。
