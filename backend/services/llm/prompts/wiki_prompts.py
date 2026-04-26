"""Wiki 页面的 prompt 模板。

三层生成模式：
1. Outliner（OUTLINE_*）：一次调用决定核心架构章节 + 专题深入议题
2. 模块/章节/专题（MODULE_/CHAPTER_/TOPIC_*）：基于 outline 并发生成内容
3. 概览页（OVERVIEW_*）：所有子页生成完后收口，做首页

约定各页面 LLM 以严格 JSON 返回：
    {"content_md": "...", "code_refs": {"ref_1": {"symbol": "foo"}}}

Outliner 的 JSON 结构不同，独立定义见 outliner.py。
"""

from __future__ import annotations


# --------- 输出约束（内容页共用） ---------

COMMON_OUTPUT_RULES = """\
## 输出约束（必须严格遵守）
只输出一个 JSON 对象，不要 markdown 包裹，不要任何额外解释。结构如下：

{
  "content_md": "<Markdown 字符串，即页面正文>",
  "code_refs": {
    "ref_1": {"symbol": "<符号名>", "file": "<相对路径，可选>"},
    "ref_2": {"file": "<相对路径>"}
  }
}

### content_md 书写规则
- 使用 GitHub Flavored Markdown
- 页面跳转用 `[显示文字](#wiki:<page_id>)`，page_id 必须来自下文「可用页面 id」列表
- 代码引用用 `[显示文字](#code:ref_N)`，ref_N 必须在 code_refs 中声明
- 允许使用表格、代码块、列表；酌情使用 mermaid 流程图（```mermaid ... ```）
- 不要在 content_md 里写行号（例如"第 45 行"），行号由服务端从 AST 补齐

### code_refs 书写规则
- key 任意，但要与 content_md 里 `#code:xxx` 对应
- 每个 ref 至少提供 `symbol`（优先）或 `file`；如果只给 file，表示引用整个文件
- 不要编造不存在的符号；只引用「上下文」中明确列出的符号
"""


# --------- Outliner（大纲生成） ---------

OUTLINE_SYSTEM = """你是一位资深技术写作编辑，擅长根据一个软件项目的结构和代码特征，
规划一份"系统架构解读 + 设计巧思深入"的文档大纲。
你的任务是决定：这个项目的核心架构应该拆成哪几章来讲，以及哪些设计值得开专题深入。
用中文回答，严格以 JSON 输出。"""


def build_outline_prompt(
    project_name: str,
    project_summary: str | None,
    modules_text: str,
    module_deps_text: str,
    run_hints_text: str,
    stats_text: str,
) -> tuple[str, str]:
    ps_section = f"\n## 项目摘要\n{project_summary}\n" if project_summary else ""

    user = f"""请为项目「{project_name}」规划 Wiki 文档的大纲。
文档固定有三大类：概览 / 核心架构 / 模块详解 / 专题深入。其中模块页已由代码结构自动生成，
你只需要决定「核心架构」下的章节，以及「专题深入」下的议题。
{ps_section}
## 模块清单
{modules_text}

## 模块间调用关系
{module_deps_text}

## 运行线索（Makefile / 入口文件 / 配置）
{run_hints_text}

## 项目统计
{stats_text}

## 任务

输出两个列表：

### chapters（核心架构章节，3-5 个）
- 系统架构视角的连贯叙事，每章聚焦一个主题（如"主循环与事件流"、"数据持久化链路"、"多 Agent 协作"）
- 避免与「模块详解」重复——模块页已经逐个讲过，这里要做**跨模块的整合**
- 如果项目较小/架构扁平，宁可输出 3 章，不要凑数
- title 建议带编号（例如 "1. 系统主循环"），brief 2-3 句说明这一章要覆盖什么

### topics（专题深入，2-4 个）
- 挖掘项目的**设计巧思、突出优点**（独特的并发控制、状态机、安全策略、性能优化、抽象设计等）
- 每个专题做深度分析——**为什么这样做 / 权衡了什么**，而不是流水账式描述
- 如果项目平平无奇找不到亮点，可以输出 2 个常见但写得好的主题；**宁缺毋滥**
- title 要体现主题（例如 "上下文工程的四层压缩"），brief 2-3 句说明角度

## 输出约束（必须严格遵守）

只输出一个 JSON 对象，不要 markdown 包裹，不要任何额外解释。结构如下：

{{
  "chapters": [
    {{"title": "1. ...", "brief": "..."}},
    {{"title": "2. ...", "brief": "..."}}
  ],
  "topics": [
    {{"title": "...", "brief": "..."}}
  ]
}}

- chapters 长度必须在 3 到 5 之间
- topics 长度必须在 2 到 4 之间
- 每个 title 不超过 30 字；brief 控制在 2-3 句、不超过 120 字
"""
    return OUTLINE_SYSTEM, user


# --------- 模块页 ---------

MODULE_PAGE_SYSTEM = """你是一位资深软件架构师，擅长把一组相关文件抽象为一个"模块"，
并向学习者讲清楚这个模块的职责、组成与对外关系。用中文回答。"""


def build_module_page_prompt(
    module_name: str,
    module_description: str,
    module_code_text: str,
    cross_module_interaction_text: str,
    readme_snippet: str | None,
    allowed_page_ids: list[str],
    module_paths: list[str],
    min_code_refs: int,
) -> tuple[str, str]:
    """模块页 prompt：两段式（速览区固定 + 详解区自由）。

    单次 LLM 调用；JSON 输出字段顺序固定为
    speed_summary → detail_md → code_refs → reading_guide
    （让 LLM 写 reading_guide 时已经"看到"自己刚写的 detail_md）。
    """
    readme_section = (
        f"\n## 本模块相关的 README 片段\n{readme_snippet}\n"
        if readme_snippet else ""
    )
    allowed = "\n".join(f"- {pid}" for pid in allowed_page_ids) or "（无）"
    paths_block = "\n".join(f"- {p}" for p in sorted(module_paths)) or "（无）"

    user = f"""请为下述功能模块生成「模块页」。

## 模块信息
- 名称：{module_name}
- 一句话描述：{module_description}

## 模块完整源码
{module_code_text}

## 与其他模块的交互（**仅供参考，最终渲染由代码生成，你不必复述这段**）
{cross_module_interaction_text}
{readme_section}
## 模块包含的文件路径（`speed_summary.file_roles` 的 key 必须为这些 path，不可增删）
{paths_block}

## 可用页面 id（跳转目标，**仅包含其他模块**——本模块只能引用同级模块）
{allowed}

## 任务

按下方 schema 输出 JSON。**字段顺序不可调整**——写到 reading_guide 时你应当先看一眼自己刚写的 detail_md，再做出取舍判断。

### 1. `speed_summary`（速览区，固定结构）

`tagline`：一句话定位（≤30 字）。可参考"模块描述"，但允许重述得更精炼。
`file_roles`：dict，key 必须为上面"模块包含的文件路径"列表里的每一个 path（不可增删），value 为该文件的一行职责说明（≤25 字，从源码读出来的真实职责，不要泛泛而谈）。

### 2. `detail_md`（详解区，**自由发挥**）

写一份**让读者真正读懂这个模块**的详解，目标是覆盖到位：
- **核心抽象与组件**——本模块靠哪几个数据结构 / 类 / 函数撑起来
- **关键流程**——从入口到完成的完整链路（含分支、错误路径）
- **不显然的设计取舍**——为什么 X 不 Y、为什么这个值不那个值
- **边界情况与失败模式**——并发、过期、跨边界、异常未捕获时怎么走

读完之后，**新人应当能做到三件事**：
1. 清楚这个模块在做什么、为什么这样切
2. 改代码时知道该改哪几个文件、动哪段
3. 理解 1-2 个非显然的设计决策（不是"是什么"而是"为什么"）

**篇幅由覆盖度决定**——内容深就多写、内容平就少写；不要为追求"短"省略关键内容，也不要为凑字数复述源码。

**开篇必填：引言段 + 路线图**：
- 第一个 H2 之前先写 **1-2 段引言**——讲清楚本模块的核心抽象、模块边界（什么在内、什么在外）、读者读完后能拿走什么
- 引言之后给一句**路线图**——例如「§1 拆解... §2 分析... §3 提炼...」——让读者知道接下来的阅读路径
- 引言不算 H2，直接以段落形式写在最开头

**多层次切分（必填，重要）**——这是高质量技术文档的核心标志：

**章节密度的硬下限**（按文件数粗略估计）：
- ≤6 文件 → **至少 3 个 H2**
- 7-12 文件 → **至少 4 个 H2**
- ≥13 文件 → **至少 5 个 H2**
- 不要把多个独立话题塞在一个 H2 下用 H3 凑数。如果你想写「核心链路 + 多层防御 + 订单 ID + 锁实现 + 演进轨迹」5 件事，就给 5 个 H2，不要把它们都塞进「核心链路」一个 H2

**层级使用规则**：
- **H2** 是大节（独立的一个完整话题）；至少 2 个 H2 必须用 `### ` H3 子节切分
- **H3** 在 H2 内承担"具体话题"切分。不要把一个 H3 写成 200-400 字的连续大段
- **H4** 在 H3 内做更深一层切分——**全文至少出现 2 次 H4**。触发条件：
  - 一个 H3 内有 2+ 个明显独立的子话题（如「替代方案对比」下「为什么不用 X」「为什么不用 Y」）
  - 一个 H3 描述的失败模式有"主路径"和"补偿路径"两条线
  - 一个 H3 内同时讨论"是什么"和"为什么不是别的"
- 示例结构（节选自真实模块页）：
  ```
  ## 1. 双拦截器协作模型
  ### 1.1 RefreshTokenInterceptor：上下文恢复
  ### 1.2 LoginInterceptor：强制鉴权
  ### 1.3 ThreadLocal 清理责任

  ## 2. 异步下单
  ### 2.1 为什么不是 BlockingQueue
  ### 2.2 Pending List 与异常补偿
  #### 主循环 vs PEL 循环的职责分离
  #### 失败模式：无最大重试上限
  ```
- 设计洞察节是编号列表，不需要 H3

**视觉元素多样化**——光靠段落 + 列表会让正文显得平：
- **表格**（强烈建议）：用于对比、配置常量、阈值、失败语义对比。**全文应当出现 1-3 张表**——例如「v1/v2/.../v现役 + 致命缺陷」、「失败层 / 失败时返回 / 失败成本」、「常量名 / 值 / 用途」。一张好的对比表胜过 200 字平铺
- **ASCII 框图**（适合时使用）：当内容是**比特布局 / 内存结构 / 三层架构示意**时，ASCII 框图比 mermaid 更清晰。例如：
  ```
  ┌─ 64 位 ID ───────────────────────────────────────┐
  │ [1 位符号] [31 位时间戳]    [32 位日序列]           │
  └──────────────────────────────────────────────────┘
  ```
- **mermaid**：适合时序、流程、状态机（已在下方独立指引）
- 三种视觉元素**各司其职、不互相替代**——一份高质量模块页通常 mermaid + 1-2 张表 + 偶尔 ASCII 框图

**演进轨迹的位置（重要）**：如果代码里有 2+ 历史版本（注释掉的旧实现 / `if (false)` / TODO 标记），**演进轨迹应当作为开篇 H2 章节**（如 `## 1. 演进轨迹：从 X 到 Y`），不是放在结尾的设计洞察里——因为它给后续章节提供"为什么长这样"的上下文，是叙事的灵魂线索

**引用块（`> `）作为视觉侧栏（必填，重要）**：
- 当某条信息属于以下类型时，**应当用引用块从正文剥离出来**——视觉上立刻分层，让正文保持主线流畅：
  - **细节**：补充性的小观察（`> 细节：Cluster 兼容性问题——Collections.emptyList() 意味着...`）
  - **失败模式警示**：如果这一步出错会发生什么（`> 失败模式警示：如果 createVoucherOrder 持续抛异常...`）
  - **设计权衡**：取舍背后的成本/收益（`> 设计权衡：锁牺牲了灵活性，换来了缓存稳定性`）
  - **关键观察**：从代码里读出来的非显然事实（`> 关键观察：v2 → v3 是把锁换得更好但没解决根因`）
  - **小结**：节末用一句话拎清楚的判断（`> 小结：SimpleRedisLock 是教学样本，Redisson 是生产实现`）
- **目标频度**：全文应当出现 **3-8 处**引用块。一处都没有 = 视觉层次丢了
- 引用块**不是装饰**——只在正文里强行展开会打断节奏的内容上使用；一节里 1-3 处合适，全节都用反而失去层次

**「概览—细节」节奏（每个 H2 必填）**：
- **每个 H2 进入第一个 H3 之前，必须先有一段 2-4 句的引导段**——告诉读者本节要看什么、为什么这么切、和上一节的关系
- 引导段不复述章节标题，而是给一个"对话式"的开场：
  ```
  ## 3. 异步下单：Stream + 单线程消费

  资格判定通过后，订单落库**完全异步**——同步路径返回的瞬间，DB 还没写。
  Stream + Worker 这套组合是 v4 的 BlockingQueue 升级而来，每一处选择都对应 v4 踩过的坑。

  ### 3.1 为什么不是 BlockingQueue
  ...
  ```
- 引导段也是引出本节"为什么值得看"的钩子——避免读者扫到 H2 标题不知道里面在讲什么

**结构自由度**：
- **你决定分几段、叫什么标题、按什么顺序**——根据本模块特性挑选合适的角度

**叙事递进**：各 H2 之间最好有**逻辑递进**（前一节为后一节铺上下文，而非平行罗列）。但没有真实递进就别硬凑——平行胜过假装递进。

**结尾节「设计洞察」**（强烈建议）：
- 模块有**非平凡的设计决策**（不对称的失败模式、隐形约束、多层防御、演进遗留问题等）时，最后一节叫「设计洞察」或「关键观察」，编号列表 **5-8 条**
- **每条必须是「为什么这样做」而非「是什么」**——这是最容易踩坑的地方：
  - ✗ "使用 Lua 脚本保证原子性"（这是"是什么"）
  - ✓ "Lua 替代 MULTI/EXEC 的根因是事务不能中途分支——而秒杀必须有 if 库存>0 then 扣减 else 失败 这种条件分支"（这是"为什么"）
  - ✗ "采用 Redis Stream 实现异步处理"
  - ✓ "Stream 替代 BlockingQueue 的核心收益是 PEL 而不是异步本身——PEL 让消费但未 ACK 的消息留下来等待重试，这是 at-least-once 语义的根基"
- 每条结构：**一句结论 + 1-2 句具体分析**（含权衡 / 代价 / 对比）
- 设计洞察是其他正文章节的**元结论**——读者跳过正文也能从这节抓到核心判断
- 模块平平无奇没什么可提炼的，**直接不写这节**——禁止凑数

**深度维度**（每段必须触达至少一个，否则就是在复述源码）：

每段不要只回答"是什么"。在合适的地方追问以下任一深度维度：
- **边界情况**：极端输入、并发、过期、空值、跨边界（跨月/跨年/跨区）时这段代码怎么走？
- **失败模式**：如果这一步出错（网络抖动 / Redis 丢失 / 进程被杀 / 异常未被 `afterCompletion` 调用），后果是什么？是降级、报错、还是静默错乱？
- **替代方案对比**：为什么**不用** X？X 的来源有两类，**都要看**：
  1. **领域常见替代**：JWT 而非 Redis Session / Spring Security 而非自己写拦截器 / DB 自增 ID 而非 UUID / B+ 树而非 BitMap
  2. **代码内的历史痕迹**——这是更高价值的角度：被 `/* */` 注释掉的旧实现、`if (false)` 死分支、TODO 标记的未来方向、相邻文件中的类似但被废弃的类。**这些是模块演进的真实证据**，往往比领域常见替代更有针对性。如果模块里有 2 个以上历史版本，**把它们按时间顺序整理成「演进轨迹」表**作为开篇章节（v1/v2/.../v现役 + 各自的致命缺陷），是单模块文档里能写出的最高价值角度

- **多层防御的失败假设拆解**：当模块包含 2+ 层冗余防御（例如「Redis 校验 + 分布式锁 + DB 唯一约束」「Lua 原子去重 + Worker 重读 DB + SQL 乐观锁」），**应当用一张表逐层列出每一层防的是什么具体失败假设**——而不是笼统说"多层防御"。表格示例：
  ```
  | 防御层 | 防御失败时返回 | 它在防什么具体假设 |
  |---|---|---|
  | Lua 原子判定 | 错误码 1/2 | Redis 单线程内不可能有竞态 → 防"两次往返间被插队" |
  | Redisson 用户锁 | log.error + return | Lua 已去重但极端时序下 PEL 重试可能并发 → 防"多 Worker 重复消费" |
  | DB stock>0 兜底 | log.error + return | Redis/锁都被绕过（手工 RPC、消息伪造）→ 防"绕过前两层的非法路径" |
  ```
  这张表的价值在于：让读者明白每一层都在防一类**不同的**失败，没有一层是冗余的。这是把"多层防御"从"听起来很厉害"变成"有具体证据"的关键

**这是把"复述代码"和"理解设计"区分开的关键**。每个 H2 至少要触达一个维度。

**标题规范**：
- **顶层标题统一用 `## `**（H2），不要直接以 H3 起头作主题
- **禁用通用 H2 标题**：「概述 / 介绍 / 详情 / 总结 / 说明 / 内容 / 简介 / 概览」等空洞标题
- **禁止 emoji 起头**：标题不要用 emoji 装饰（🔑📅🛡️ 等）；正文也尽量少用
- 每个 H2 必须以**具体观察**起手，不准空话铺垫（如"本模块非常重要"这类）

**反退化清单**：
- **禁止重复速览区事实**：不要再列一遍文件清单 / 不要再罗列跨模块依赖
- **禁止浮夸炫技词汇**——只陈述事实，不评价；不要把入门级做法（加盐 MD5 / JWT / Redis 缓存 / ThreadLocal 上下文）包装成亮点
- **禁止猜测**——所有事实陈述必须能在源码或上下文中找到依据；**不要从模块编号、文件名、变量名脑补业务含义**（例如不要说"推测 `module_4` 涉及交易"或"看名字应该是处理评价的"）；**不要从你训练数据里编"这个领域的常见值"**（如 TTL / 端口 / 默认配置）——值在外部常量文件里看不到时直接说"由 XxxConstants 定义"，不要自己填数

**关键代码节选**（**1-3 处**，除非模块全是 CRUD/Mapper 接口）：
- 详解区中**应有 1-3 处** 5-15 行的源码片段（fenced code block，标好语言）——**每个含算法 / 状态机 / 关键约束的 H2 都应当配 1 段源码举证**
- 贴的代码要有上下文交代——前面一句话讲**为什么这段值得贴**，后面一句话点出**关键观察**
- 这是"举证"，不是"复述"——**禁止整段抄文件**，也不要把已能用 `[..](#code:ref_X)` 锚点引用的内容再贴一遍

**Mermaid 流程图**（应当用，不是"酌情"）：
- 模块若有 **数据流 / 执行链 / 状态机 / 三层架构 / 调用拓扑** 这种**结构性逻辑**，**应当**画 mermaid 图——`flowchart`、`sequenceDiagram`、`stateDiagram` 都可以
- 图是叙事核心，不是装饰；放在第一次需要"读者建立空间感"的段落里
- 模块只是几个工具函数堆在一起、没有结构性逻辑，就**不画**——禁止为凑而画

**代码锚点规范（硬约束）**：
- **必须严格 ≥ {min_code_refs} 个 `[..](#code:ref_X)` 锚点**——少于此数视为不合格输出
- 挑模块里最值得点开看的具体符号位置（关键算法函数、状态机、隐式约束所在的行）

**写完 detail_md 后必须执行的自查清单**（顺序检查）：
1. **数 ref**：从 ref_1 到 ref_N 数一遍，N 必须 ≥ {min_code_refs}。如果不够，回去补——常见漏算：辅助工具类（`RedisIdWorker.nextId`、`SimpleRedisLock.unlock`、`addSeckillVoucher`）、被引用的常量（`BEGIN_TIMESTAMP`）、状态字段（`SECKILL_SCRIPT` 静态加载块）。一个看似"普通"的辅助函数 + 一个隐式常量 + 一个状态字段 = 3 个补救锚点
2. **数引用块**：全文 `> ` 引用块应当 3-8 处。如果是 0-2 处，回去把至少 2 个"普通段落里的设计权衡 / 失败模式警示"提取成引用块
3. **数表格**：除速览区外应当有 1-3 张表。如果是 0 张，看看是否有「演进版本」「失败语义对比」「常量配置」可以表格化
4. **数 H2**：按章节密度下限自查（≤6 文件→3 个；7-12 文件→4 个；≥13 文件→5 个）

**锚点显示文字规范**：
- **必须是符号名 / 类名 / 具体行为短语**：`[saveOrUpdate()](#code:ref_X)` ✓、`[拦截器注册顺序](#code:ref_X)` ✓
- **禁止用叙事性修饰短语作为显示文字**：`[依赖幂等性与最终一致性](#code:ref_X)` ✗、`[是典型读写分离决策点](#code:ref_X)` ✗——这种显示文字让读者点开前根本不知道会看到什么

**跨模块跳转**：
- 用 `[..](#wiki:module_N)`，**只能引用上面"可用页面 id"列表里的 module_***——不要链接到 overview / category / chapter / topic / file 页

若源码中某文件被截断，仍可基于已展示部分作答；不要凭空补全未展示的内容。

### 3. `code_refs`

为 detail_md 里每个 `#code:ref_X` 提供解析依据。每个 ref 至少给 `symbol`（优先）或 `file`。**只引用源码里真实存在的符号**。

### 4. `reading_guide`（≤80 字；**写完 detail_md 之后再写**）

回看你刚写的 detail_md，挑出**最值得读的一节**并说明理由——形式自由：
- 场景化导引：「想 A 看「X」/ 想 B 看「Y」」（2-3 行）
- 重点提示：直接指出关键观察点

**软约束**：
- 必须做出取舍判断，**禁止说"全文都很重要"**之类
- **禁止纯粹复述详解区 H2 标题**（不要变成迷你目录）
- 模块太简单、确实没什么可引导的，**直接输出空字符串 `""`**，本节将不渲染

---

## 输出约束（必须严格遵守）

只输出一个 JSON 对象，不要 markdown 包裹，不要任何额外解释。结构如下（**字段顺序不可调整**）：

{{
  "speed_summary": {{
    "tagline": "<≤30 字定位>",
    "file_roles": {{
      "<path1>": "<≤25 字职责>",
      "<path2>": "..."
    }}
  }},
  "detail_md": "<详解区 markdown>",
  "code_refs": {{
    "ref_1": {{"symbol": "<符号名>", "file": "<相对路径，可选>"}},
    "ref_2": {{"file": "<相对路径>"}}
  }},
  "reading_guide": "<≤80 字阅读引导，可为空字符串>"
}}

不要在 detail_md 里写行号（例如"第 45 行"），行号由服务端从 AST 补齐。
"""
    return MODULE_PAGE_SYSTEM, user


# --------- 章节页（核心架构） ---------

CHAPTER_PAGE_SYSTEM = """你是一位资深技术作家，擅长从系统架构视角讲解一个软件项目。
你正在为一份项目 Wiki 的「核心架构」栏目写一章。
你的视角是**跨模块的系统视角**，讲的是组件如何协作、数据如何流动、关键抽象如何搭起来。
读者是想系统性理解项目的新同事或技术决策者。用中文回答，语气克制、避免套话。"""


def build_chapter_page_prompt(
    chapter_title: str,
    chapter_brief: str,
    project_name: str,
    project_summary: str | None,
    modules_text: str,
    module_deps_text: str,
    run_hints_text: str,
    allowed_page_ids: list[str],
) -> tuple[str, str]:
    ps_section = f"\n## 项目摘要\n{project_summary}\n" if project_summary else ""
    allowed = "\n".join(f"- {pid}" for pid in allowed_page_ids) or "（无）"

    user = f"""请为项目「{project_name}」的「核心架构」写一章：

## 本章主题
**{chapter_title}**

## 写作指引
{chapter_brief}
{ps_section}
## 模块清单（可引用）
{modules_text}

## 模块间调用关系
{module_deps_text}

## 运行线索
{run_hints_text}

## 可用页面 id（跳转目标）
{allowed}

## 任务
围绕本章主题写一篇连贯的技术文章（600-1200 字）：
- 从读者视角出发，先交代问题，再展开方案
- 跨模块引用用 `[模块名](#wiki:module_N)`
- 关键代码位置用 `[显示文字](#code:ref_N)` 锚点
- 可以用 mermaid 画流程图/时序图
- **不要泛泛而谈**——如果找不到项目里对应的设计，宁可缩短篇幅
- **不要重复模块页的内容**——这里要做的是跨模块的整合叙事

{COMMON_OUTPUT_RULES}
"""
    return CHAPTER_PAGE_SYSTEM, user


# --------- 专题页（专题深入） ---------

TOPIC_PAGE_SYSTEM = """你是一位资深技术评论者，擅长挖掘一个项目的设计巧思并做深度分析。
你正在为一份项目 Wiki 的「专题深入」栏目写一篇专题。
你的视角是**聚焦与批判**：围绕一个具体的设计点，讲清楚它是什么、为什么这样做、权衡了什么。
读者是资深工程师，不需要铺垫基础概念。用中文回答，语气犀利、避免空话。"""


def build_topic_page_prompt(
    topic_title: str,
    topic_brief: str,
    project_name: str,
    project_summary: str | None,
    modules_text: str,
    module_deps_text: str,
    allowed_page_ids: list[str],
) -> tuple[str, str]:
    ps_section = f"\n## 项目摘要\n{project_summary}\n" if project_summary else ""
    allowed = "\n".join(f"- {pid}" for pid in allowed_page_ids) or "（无）"

    user = f"""请为项目「{project_name}」的「专题深入」栏目写一篇专题：

## 本专题主题
**{topic_title}**

## 写作指引
{topic_brief}
{ps_section}
## 模块清单（可引用）
{modules_text}

## 模块间调用关系
{module_deps_text}

## 可用页面 id（跳转目标）
{allowed}

## 任务
围绕本专题写一篇深度分析（500-1000 字）：
- **是什么**：一段话描述这个设计点/巧思
- **为什么**：分析动机和解决的问题
- **怎么做的**：具体的实现手法，可用 `[显示文字](#code:ref_N)` 锚点引用关键代码
- **权衡**：这样设计牺牲了什么、有什么潜在风险
- **可选**：对比其它常见做法
- 不要吹捧也不要轻易贬低；只陈述你看到的事实和合理推断

{COMMON_OUTPUT_RULES}
"""
    return TOPIC_PAGE_SYSTEM, user


# --------- 概览页 ---------

OVERVIEW_PAGE_SYSTEM = """你是一位资深技术作家，擅长为一个项目写"第一印象"式的概览页。
目标是让读者用三分钟了解项目做什么、架构如何、怎么跑起来。用中文回答，语气简洁。"""


def build_overview_page_prompt(
    project_name: str,
    project_summary: str | None,
    modules_text: str,
    module_deps_text: str,
    chapters_text: str,
    topics_text: str,
    root_readme: str | None,
    tech_stack_text: str,
    config_text: str,
    run_hints_text: str,
    stats_text: str,
    allowed_page_ids: list[str],
) -> tuple[str, str]:
    readme_section = (
        f"\n## 根 README\n```\n{root_readme}\n```\n"
        if root_readme else ""
    )
    ps_section = f"\n## 已有项目摘要（供参考）\n{project_summary}\n" if project_summary else ""
    allowed = "\n".join(f"- {pid}" for pid in allowed_page_ids) or "（无）"

    user = f"""请为项目「{project_name}」生成「概览页」的内容。
{ps_section}
## 核心模块及摘要
{modules_text}

## 模块间高层依赖
{module_deps_text}

## 已生成的核心架构章节（供你在概览中引导）
{chapters_text}

## 已生成的专题深入议题
{topics_text}
{readme_section}
## 技术栈线索（来自 requirements.txt / package.json / 等）
{tech_stack_text}

## 配置项（来自 .env.example 等）
{config_text}

## 运行线索（Makefile / package.json scripts / 入口文件片段）
{run_hints_text}

## 项目统计
{stats_text}

## 可用页面 id（跳转目标）
{allowed}

## 任务
按下述结构写概览页：
1. **项目介绍**：基于 README 与摘要，2-3 段说清楚做什么、解决什么问题
2. **整体架构**：叙事风格描述各模块如何协作；鼓励引用核心架构章节 `[章节名](#wiki:chapter_N)` 作为深入阅读入口
3. **核心模块**：列表列出每个模块，每项一句话介绍并用 `[模块名](#wiki:module_N)` 链接
4. **值得一看的专题**：把 topic 列出来，每项一句话勾人；用 `[专题名](#wiki:topic_N)` 链接
5. **项目元信息**：分三小节——技术栈 / 配置项 / 如何运行；如何运行一节必须基于「运行线索」，线索不足就坦白说"启动方式不明确"，不要瞎编

{COMMON_OUTPUT_RULES}
"""
    return OVERVIEW_PAGE_SYSTEM, user
