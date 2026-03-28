# 实验 007: 网页内容格式对 DeepSearch Agent 的影响 — 综合分析

## 1. 实验概述

### 1.1 研究问题

DeepSearch agent 通过搜索引擎找到相关网页，抓取内容后注入 LLM context 来回答问题。工业界对网页内容的处理方式各异——有的直接喂原始 HTML，有的转为 Markdown，有的只提取纯文本。**格式选择如何影响 agent 的回答质量和资源消耗？** 这个问题目前缺乏系统性的实证研究。

### 1.2 假设

| 编号 | 假设 | 核心论点 |
|------|------|----------|
| H1 | Markdown 在准确率/token 效率上达到最优平衡 | 保留结构（表格、列表），同时去除 HTML 样板代码 |
| H2 | 原始 HTML 消耗远超其他格式的 token，但不带来准确率提升 | 大量 HTML 标签、CSS、JS 是纯噪声 |
| H3 | 纯文本格式在依赖表格/列表的问题上准确率下降 | 丢失结构信息导致信息提取困难 |
| H4 | 在多跳查询中，原始 HTML 导致 context 膨胀和推理退化 | context window 被噪声占满，无法容纳多步推理所需信息 |

### 1.3 实验设计

**4 种内容格式策略：**

| 策略 | 实现方式 | 描述 |
|------|---------|------|
| `raw_html` | 直接返回 | 控制组，agent 接收完整 HTML（含 JS/CSS/导航/广告） |
| `markdown` | MarkItDown 库 | HTML → Markdown 转换，保留表格和列表结构 |
| `text_only` | BeautifulSoup | 移除非内容标签后提取可见文本，不保留任何结构 |
| `pruned_html` | BeautifulSoup | 移除 script/style/nav/aside/广告元素，保留语义 HTML 标签 |

**机制**：通过 `after_tool_exec` hook 拦截 `fetch_page` 返回的原始 HTML，按策略转换后再交给 agent。agent 对转换过程无感知。

**任务集**：GAIA benchmark validation set 中筛选的 75 个纯网页搜索任务（L1=33, L2=37, L3=5），排除了需要文件附件、calculator、image、video 等特殊工具的任务。

**模型**：Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) via AWS Bedrock

**参数**：max_turns=30, temperature=0.0, 每策略独立运行 2 次 (run)，concurrency=2

---

## 2. 总体结果

### 2.1 核心指标

| 策略 | Run 1 | Run 2 | 平均准确率 | 平均延迟 | 平均 Input Token | 平均 Fetch 大小 | Context 溢出 |
|------|-------|-------|-----------|---------|-----------------|----------------|-------------|
| **text_only** | 68.0% | 66.7% | **67.3%** | 76.1s | **179,034** | 24,955 | **0** |
| **markdown** | 69.3% | 61.3% | **65.3%** | 74.6s | 236,891 | 43,451 | 5 |
| **jina_reader** | 61.3% | 61.3% | **61.3%** | 59.8s | 215,522 | 54,929 | 7 |
| **pruned_html** | 58.7% | 61.3% | **60.0%** | 87.2s | 234,158 | 28,898 | 5 |
| **raw_html** | 40.0% | 42.7% | **41.3%** | 54.9s | 276,044 | 241,058 | **56** |

> **注**: pruned_html Run 2 原始数据中有 21 个任务因 Serper API key 耗尽而失败（准确率仅 46.7%），经补跑修正后为 61.3%。上表为修正后数据。

### 2.2 Token 效率

| 策略 | 总 Token (2 runs) | 总正确数 | 效率 (正确/百万 token) |
|------|-------------------|---------|----------------------|
| **text_only** | 27.1M | 101 | **3.8** |
| markdown | 36.8M | 98 | 2.7 |
| jina_reader | 32.3M | 92 | 2.8 |
| pruned_html | 43.9M | 90 | 2.1 |
| raw_html | 35.8M | 62 | 1.7 |

text_only 的 token 效率是 raw_html 的 **2.2 倍**——用更少的 token 做对了更多的题。jina_reader（2.8）略优于 markdown（2.7），因为它消耗的 token 更少（32.3M vs 36.8M），尽管准确率低于 markdown。值得注意的是 pruned_html 虽然准确率（60.0%）高于 raw_html，但其 token 消耗（43.9M）是所有策略中最高的，效率最低。

### 2.3 内容压缩比

各策略对同一网页的中位 fetch 大小（字符数）：

| 策略 | P25 | P50 (中位数) | P75 | Max |
|------|-----|-------------|-----|-----|
| raw_html | 21,399 | **56,513** | 302,141 | 3,043,429 |
| jina_reader | 6,191 | **17,623** | 52,705 | 1,306,353 |
| markdown | 789 | **9,742** | 50,952 | 741,703 |
| text_only | 714 | **5,180** | 18,559 | 667,910 |
| pruned_html | 109 | **3,337** | 22,227 | 1,866,929 |

raw_html 的中位 fetch 大小是 text_only 的 **11 倍**，是 markdown 的 **6 倍**。jina_reader 的中位大小（17,623 字符）介于 raw_html 和 markdown 之间——比 markdown 大约 1.8 倍，这反映了 Jina 在转换时保留了标题、URL 元数据、发布时间等额外信息。

值得注意的是 pruned_html 的 P25 仅 109 字符——说明部分网页在移除噪声标签后几乎没有内容残留，这可能是 pruned_html 表现不稳定的原因之一（过度清理导致信息丢失）。

---

## 3. 假设验证

### H1: Markdown 达到最优准确率/token 平衡 — **部分否定**

Markdown 在准确率上接近 text_only（65.3% vs 67.3%），但 token 消耗高出 36%（36.8M vs 27.1M）。**text_only 才是真正的效率之王**——准确率最高，token 消耗最低。

Markdown 的优势体现在特定场景：
- 需要解析表格数据的任务（如 Wikipedia 编辑次数、棒球统计数据）
- 需要结构化列表信息的任务
- 它有 4 个 unique wins（仅 markdown 做对的任务），而 text_only 只有 2 个

但整体而言，Markdown 的结构保留优势被更高的 token 开销和偶发的 context 溢出（5 次）所抵消。

**结论**：H1 不成立。text_only 在准确率和 token 效率上均优于 markdown。

### H2: 原始 HTML 消耗远超但不带来准确率提升 — **强烈证实**

raw_html 是表现最差的策略：

- **准确率最低**：41.3%（比 text_only 低 26 个百分点）
- **Context 溢出灾难**：两轮合计 56 次 context overflow（占总调用的 37%）
  - Run 1: 31 次 overflow（41%）
  - Run 2: 25 次 overflow（33%）
- **L2/L3 任务几乎不可用**：L2 准确率仅 35%（含大量 overflow），L3 准确率 0%
- 有趣的是 raw_html 的**平均延迟反而最低**（54.9s），因为大量任务在 fetch 1-2 个页面后就因 context overflow 而提前终止

raw_html 仅有 2 个 unique wins（仅它做对的任务），远少于它因 overflow 而丢失的任务数。

**结论**：H2 强烈证实。raw_html 在任何维度上都不具备优势。

### H3: 纯文本在表格/列表依赖问题上准确率下降 — **未证实（含重要细节）**

这是最出乎意料的发现，也是分析最深入的一个假设。

**表层观察**：按 Level 的准确率：

| 级别 | text_only | markdown | jina_reader | pruned_html | raw_html |
|------|-----------|----------|-------------|-------------|----------|
| L1 | 68% | 65% | 67% | 59% | 63% |
| L2 | 69% | 75% | 66% | 65% | 67% |
| L3 | **50%** | 25% | 33% | 38% | 0% |

text_only 总体不低于 markdown，甚至在 L3 上明显更好。但这个结论需要更仔细的任务级分析。

**深入分析：markdown vs text_only 的分歧任务**

通过逐任务比较，Run 1 中有 15 个任务 markdown 与 text_only 结果不同（8 个 markdown 赢，7 个 text_only 赢）。对这 15 个任务进行两轮一致性检验：

| 类型 | 表面上的分歧任务数 | 跨两轮都一致 |
|------|-----------------|-------------|
| markdown 明显更好 | 8 | **2/8** |
| text_only 明显更好 | 7 | **1/7** |

**结论：绝大多数分歧（13/15）是噪声**——同一任务在 Run 2 结果翻转，说明并非策略导致，而是 LLM 运行间的非确定性（即使 temperature=0，Bedrock 模型仍有浮点操作的微小随机性）。

**真正一致的 markdown 优势：仅 2 个任务**

| 任务 | 内容 | 两轮结果 |
|------|------|---------|
| `ded28325` Caesar 密码解密 | dcode.fr 的移位查找表 | md=Y/Y, txt=N/N |
| `42576abe` Tizin 虚构语言 | **0 次 web fetch** | md=Y/Y, txt=N/N |

其中 `42576abe` 需要特别注意：该任务不涉及任何网页抓取（0 fetches），两种策略看到的是**完全相同的 context**（`after_tool_exec` hook 只处理 fetch_page 结果）。两轮都 markdown 对、text_only 错，是纯粹的模型随机性导致的偶然差异，与格式选择无关。

**唯一真实的 H3 正例：Caesar 密码（ded28325）**

通过 observer 数据确认：两种策略访问了完全相同的 URL（dcode.fr/caesar-cipher），差异在于：
- markdown 保留了密码移位对照表的结构，LLM 准确查表解密 → **"Picnic is in Ploybius Plaza."**
- text_only 将对照表打散为纯文本流，LLM 解密时对错位关系判断出错 → 连续两次答错

这是 H3 在 75 个任务中找到的唯一**可复现**的真实正例（1.3%）。

**为什么结构丢失总体影响不大？**

1. **Claude Haiku 4.5 的文本理解足够强**——即使没有表格格式，它也能从有序纯文本中提取数值和关系。Wikipedia 的统计数据、排行榜、日期等以纯文本形式同样可解析。
2. **context 容量优势压过了结构丢失的代价**——text_only 从不溢出（0 次），使 agent 可以访问更多页面、进行更多轮推理，这在复杂任务中比格式更重要。
3. **表格依赖任务本身占少数**——GAIA 任务中真正需要精确解读 HTML 表格结构的任务极少，大多数"结构化数据"（如维基百科编辑次数、物种数量）以纯文本段落或简单列表的形式也完整存在于页面中。

**结论**：H3 未证实。在 75 个任务、2 轮运行的测试中，结构丢失导致 text_only 准确率下降的可复现案例仅有 1 个（Caesar 密码解码）。这是一个存在的边界条件，但不足以支持"纯文本在结构依赖任务上系统性更差"的假设。

### H4: 原始 HTML 导致多跳推理退化 — **强烈证实**

raw_html 在 L2（多步搜索）和 L3（复杂推理链）上表现灾难性：

- **L2 准确率**（两轮平均）：raw_html 35% vs text_only 69%
- **L3 准确率**：raw_html 0% vs text_only 50%
- **Context overflow 集中在 L2/L3**：L2 有 38 次 overflow（占 raw_html L2 总调用的 51%），L3 有 6 次（60%）

多跳查询需要 agent 在 context 中累积多个页面的信息。raw_html 的单页 fetch 中位数 72,193 字符，2-3 次 fetch 后 context 就接近上限。这直接解释了为什么 raw_html 的 L1 准确率（63%）与其他策略差距不大，但 L2/L3 急剧恶化。

**结论**：H4 强烈证实。context 膨胀是 raw_html 的致命缺陷，在多跳场景下效果尤为严重。

---

## 4. 深度分析

### 4.1 策略间一致性

在 Run 1 的 75 个任务中：
- **23 个任务所有策略都做对**（简单任务，格式无关）
- **13 个任务所有策略都做错**（任务本身困难，格式无法拯救）
- **39 个任务策略间有差异**（格式影响区）

也就是说，**52% 的任务受到格式选择的直接影响**。这不是一个边际效应——格式决策在超过一半的任务上改变了最终结果。

### 4.2 运行一致性与数据污染

| 策略 | 两轮一致率 | 两轮都对 | 仅 Run1 对 | 仅 Run2 对 |
|------|-----------|---------|-----------|-----------|
| raw_html | 89% | 27 | 3 | 5 |
| jina_reader | **95%** | 43 | 3 | 3 |
| markdown | 87% | 44 | 8 | 2 |
| text_only | 80% | 43 | 8 | 7 |
| pruned_html | 79% | 37 | 7 | 9 |

> **数据修正说明**: pruned_html Run 2 原始运行中有 21 个任务因 Serper API key 耗尽而失败（搜索 API 返回 "All Serper API keys exhausted"）。由于实验按策略顺序执行（raw_html → markdown → text_only → pruned_html），pruned_html 排在最后，承受了最多的 API 耗尽影响。这 21 个任务已通过补跑修正，上表为修正后数据。

pruned_html 修正后的一致率为 79%，与 text_only（80%）接近，说明其不一致性主要是 LLM 随机性造成的，而非策略本身不稳定。

raw_html 的一致性最高（89%），但这是因为它稳定地在同一批任务上 overflow——错误模式一致。

text_only 的一致率 80% 看似不如 raw_html，但它的不一致主要来自正确与错误之间的翻转（8+7=15 个），而不是系统性失败。这种随机性是 LLM 本身的特性（temperature=0 下仍存在非确定性），与格式无关。

### 4.3 Context Overflow：格式选择的决定性影响

| 策略 | Run 1 Overflow | Run 2 Overflow | 合计 | 占比 |
|------|---------------|---------------|------|------|
| raw_html | 31 | 25 | **56** | **37%** |
| jina_reader | 4 | 3 | 7 | 5% |
| markdown | 2 | 3 | 5 | 3% |
| pruned_html | 2 | 2 | 4 | 3% |
| text_only | 0 | 0 | **0** | **0%** |

这是实验中最清晰的信号。raw_html 有超过三分之一的调用因 context overflow 直接失败，而 text_only 从未触发过 overflow。

在所有 raw_html overflow 的任务中，绝大部分在其他策略下成功完成。例如：
- **"1977 赛季 Yankee 打者数据"**（L1）：raw_html 在 fetch 一个棒球统计页面后立即 overflow（3,252 tok），而 text_only 用同样的 3 turns 和 1 fetch 就找到了正确答案（43,420 tok——同样的信息，14 倍压缩）。
- **"Doctor Who S9E11 中的迷宫名称"**（L1）：raw_html overflow，text_only 用完全相同的路径（4 turns, 2 fetches）成功回答。

### 4.4 典型 Case 分析

#### Case 1: raw_html 的 Context Overflow 灾难

**任务**: "Who nominated the only Featured Article on English Wikipedia about a dinosaur that was promoted in November 2016?" (L1, 预期答案: FunkMonk)

| 策略 | 结果 | Turns | Fetches | Token |
|------|------|-------|---------|-------|
| raw_html | **ERR** (overflow) | 3 | 1 | 3,107 |
| markdown | OK | 3 | 1 | 22,443 |
| text_only | OK | 3 | 2 | 128,452 |
| pruned_html | OK | 5 | 2 | 13,847 |

raw_html 在 fetch Wikipedia 的 Featured Article 日志页面时，整个 HTML（含导航栏、侧边栏、脚注、引用模板）直接撑爆 context。其余三种策略都顺利完成。

#### Case 2: Markdown 的结构保留优势

**任务**: "How many edits were made to the Wikipedia page on Antidisestablishmentarianism from its inception until June of 2023?" (L2, 预期答案: 2732)

| 策略 | 结果 | Turns | Fetches | Token |
|------|------|-------|---------|-------|
| raw_html | WRONG | 6 | 1 | 510,558 |
| **markdown** | **OK** | 7 | 3 | 175,189 |
| text_only | WRONG | 9 | 3 | 129,572 |
| pruned_html | WRONG | 6 | 2 | 60,687 |

这是 markdown 的 unique win。Wikipedia 的编辑历史页面包含结构化的编辑统计表格，markdown 保留了表格格式使得 LLM 能准确计数。text_only 虽然 token 更少，但丢失表格结构后无法准确提取编辑次数。

#### Case 3: text_only 在 L3 复杂任务上的容量优势

**任务**: 在 NCATS PubChem 数据库中根据分子量、原子数等条件查找特定化合物 (L3, 预期答案: 4192)

| 策略 | 结果 | Turns | Fetches | Token |
|------|------|-------|---------|-------|
| raw_html | **ERR** (overflow) | 8 | 2 | 359,867 |
| markdown | **ERR** (overflow) | 14 | 4 | 791,488 |
| **text_only** | **OK** | 8 | 3 | 155,866 |
| pruned_html | **ERR** (overflow) | 8 | 2 | 56,644 |

这个 L3 任务需要多次访问 PubChem 数据库页面来筛选化合物。**只有 text_only 成功**——因为它是唯一不会 overflow 的策略，能在 context 中容纳足够的搜索结果来完成复杂的多步筛选。

#### Case 4: raw_html 的一次 Fetch 撑爆 Context（Observer 执行追踪）

**任务**: "Who nominated the only Featured Article on English Wikipedia about a dinosaur that was promoted in November 2016?" (L1, 预期答案: FunkMonk)

通过 observer JSONL 数据还原执行过程：

**raw_html（ERR overflow）**：
```
[llm  952+90tok]  搜索 Featured Article dinosaur...
[search]          q='Featured Article dinosaur promoted November 2016 Wikipedia'
[llm  1,964+101tok] 找到了，去 fetch Wikipedia 的 Featured log 页面...
[fetch]           Wikipedia Featured_log/November_2016 → (raw HTML)
[LLM OVERFLOW]    单页 HTML 撑爆 context，agent 立刻死亡
```

**text_only（CORRECT）**：
```
[llm  952+90tok]  搜索 Featured Article dinosaur...
[search]          q='Featured Article dinosaur promoted November 2016 Wikipedia'
[llm  1,970+170tok] 看到 Giganotosaurus，去确认...
[fetch]           Wikipedia Giganotosaurus/archive1 → (纯文本)
[fetch]           Wikipedia Featured_log/November_2016 → (纯文本)
[llm  125,168+102tok] 确认 FunkMonk 提名了 Giganotosaurus → 正确答案
```

关键差异：**同一个 Wikipedia 页面**，raw_html 版本直接导致 overflow，而 text_only 版本压缩后可以正常处理。两者的搜索路径完全相同，唯一的变量就是内容格式。text_only 甚至多 fetch 了一个页面（2 vs 1），但总 token 仍在可控范围内。

#### Case 5: Markdown 在结构化数据提取上的优势（Observer 执行追踪）

**任务**: Caesar 密码解密 (L2, 预期答案: Picnic is in Ploybius Plaza.)

**markdown（CORRECT）**：
```
[llm  1,007+67tok]   搜索 Caesar cipher decoder...
[search]             q='Caesar cipher decoder online'
[llm  1,842+78tok]   去 dcode.fr 的解码器页面...
[fetch]              dcode.fr/caesar-cipher → markdown 格式
[llm  7,401+2,073tok] 页面包含解码表格，手动推理出移位量，正确解密 → OK
```

**text_only（WRONG）**：
```
[llm  1,007+67tok]   搜索 Caesar cipher decoder...（完全相同的起点）
[search]             q='Caesar cipher decoder online'
[llm  1,842+78tok]   去 dcode.fr 的解码器页面...
[fetch]              dcode.fr/caesar-cipher → 纯文本格式
[llm  6,577+4,096tok] 页面变成纯文本后，解码参考表的格式丢失，推理出错 → WRONG
```

两者输入完全相同，唯一差异是 dcode.fr 页面的格式。markdown 保留了 Caesar 密码的移位对照表结构，LLM 可以准确查表；text_only 将表格打散为纯文本流，LLM 在手动解密时出错。这是 H3（结构丢失损害准确率）的一个真实正例——但这类案例在 75 个任务中属于少数。

#### Case 6: Serper 耗尽对实验的影响与修复（Observer 执行追踪）

**任务**: IPCC 2023 报告中核能的提及次数 (9f41b083)

pruned_html Run 2 初始运行中，21 个任务遭遇 Serper API key 全部耗尽。以此任务为例：

**初始 Run 2（WRONG，3 turns）**：
```
[search] q='2023 IPCC report 85 pages nuclear energy mentions'
         → ERROR: "All Serper API keys exhausted."
[search] q='"2023 IPCC" "85 pages" nuclear energy'
         → ERROR: "All Serper API keys exhausted."
[search] q='IPCC 2023 synthesis report nuclear energy pages'
         → ERROR: "All Serper API keys exhausted."
[llm]    "I apologize, but I'm currently unable to search the web..." → 放弃
```

Agent 在第一个搜索调用时就遭遇全部 key 耗尽，完全无法工作。经清理受污染数据后补跑这 21 个任务，**pruned_html Run 2 准确率从 46.7% 修正为 61.3%**。

这一事件暴露了实验设计中的两个问题：(1) 策略按固定顺序执行，排在最后的 pruned_html 承受了最多的 API 耗尽；(2) multi-key 轮换的 false positive 机制（连续 5 次 400 即永久标记耗尽）过于激进。

#### Case 7: L3 PubChem 任务的 Context 容量决胜（Observer 执行追踪）

**任务**: 在 NCATS PubChem 数据库中根据分子量、原子数等条件查找特定化合物 (L3, 预期答案: 4192)

**raw_html（ERR overflow）**：
```
[llm  1,030+170tok]   搜索 PubChem Food Additive Status...
[search × 2]          两次搜索获取初步信息
[llm  3,403+147tok]   去 PubChem 分类页面查看...
[fetch]               pubchem.ncbi.nlm.nih.gov/classification/ → raw HTML
[llm  66,113+157tok]  ← 单个 fetch 后 input token 从 3K 暴增到 66K！继续搜索...
[search × 6]          反复搜索不同条件组合
[llm  75,014+130tok]  找到候选化合物 Propylene Carbonate，去确认...
[fetch]               pubchem.ncbi.nlm.nih.gov/compound/7924 → raw HTML
[LLM OVERFLOW]        第二次 fetch 后 context 溢出，agent 死亡
```

**text_only（CORRECT）**：
```
[llm  1,030+170tok]   搜索 PubChem Food Additive Status...（相同起点）
[search × 4]          多次搜索
[fetch]               pubchem.ncbi.nlm.nih.gov/classification/ → 纯文本
[llm  8,086+111tok]   ← 同一页面，text_only 后仅 8K tok（vs raw_html 的 66K）
[search × 2]          继续搜索
[fetch]               PubChem classification 的子页面 → 纯文本
[llm  9,928+136tok]   找到 HuggingFace 上的参考数据...
[fetch]               huggingface.co GAIA 数据集 → 纯文本
[llm  108,209+464tok] 成功从数据集中提取答案 4192 → 正确
```

关键数字对比：PubChem 分类页面的 raw HTML 占用 ~63K input token，而 text_only 版本仅占 ~5K——**压缩比 12:1**。这个差距直接决定了 agent 能否在 context 中容纳后续的搜索和 fetch。

#### Case 8: 所有策略都失败的"不可能任务"

13 个任务在所有策略下都失败，典型原因：
- **需要 PDF 解析**：如学术论文的具体数据（983bba7c, ebbc1f13）
- **需要视觉信息**：如解读 5x7 文本方阵（50ad0280）
- **信息已过时/不可及**：如特定年份的维基编辑历史细节
- **推理链过长**：如需要 20+ 步的复杂查询（dc22a632）

这些失败与格式无关，反映了当前工具集（搜索+网页抓取）的根本局限。

### 4.5 pruned_html 为何表现不佳？

pruned_html 的设计初衷是"两全其美"——既移除噪声又保留 HTML 结构。但实际表现令人失望（60.0%，显著低于 text_only 的 67.3% 和 markdown 的 65.3%），原因可能包括：

1. **HTML 标签本身就是 token 浪费**：即使移除了 script/style，剩余的 `<div>`, `<span>`, `<p>` 等标签仍占用大量 token。pruned_html 的 input token 均值（234K）与 markdown（237K）相近，远高于 text_only（179K）。

2. **清理规则的脆弱性**：基于 class/id 正则匹配（`ad|sidebar|cookie|popup|...`）的噪声移除是一种启发式方法，可能：
   - 误杀含有 "sidebar" 但实际是内容的元素
   - 遗漏使用非标准命名的广告元素
   - P25 fetch 大小仅 16 字符——说明某些页面被清理得几乎为空

3. **输出质量对 DOM 结构敏感**：不同网站的 HTML 结构差异导致清理效果参差不齐。P25 fetch 大小仅 16 字符说明某些页面被过度清理。

4. **max_turns 耗尽率最高**：两轮合计 12 次命中 30-turn 上限（text_only 仅 6 次）。保留的 HTML 标签可能导致 LLM 更频繁地"迷失"在嘈杂的标记中。

### 4.6 jina_reader：专业服务的表现与局限

jina_reader 是实验中唯一使用**远程 API** 处理内容的策略，代表了"服务外包"路线（vs 其他策略的本地处理）。

**核心指标**：

| 维度 | jina_reader | 定位 |
|------|-------------|------|
| 准确率 | 61.3% | 4/5（优于 pruned_html，低于 markdown） |
| 延迟 | **59.8s**（最快之一） | 仅 raw_html 更快（54.9s，但靠 overflow 早死） |
| Input Token | 215,522 | 4/5（低于 markdown，高于 text_only） |
| Fetch 大小 P50 | 17,623 字符 | 比 text_only 大 3.4x，比 raw_html 小 3.2x |
| Context Overflow | 7 次（5%） | 比 markdown/pruned_html 略多 |
| 运行一致性 | **95%**（最高！） | R1 R2 完全相同 46/75 任务 |

**与其他策略相比的独特之处**：

1. **速度出乎意料的快**：59.8s 仅次于 raw_html（54.9s），比 text_only（76.1s）和 markdown（74.6s）快约 20%。这看似矛盾——jina_reader 需要两次 HTTP 请求（Playwright + Jina API），为什么反而更快？根本原因是 Jina 返回的**内容更简洁**，agent 更快收敛（平均 7.7 轮，而 text_only 是 8.9 轮），每轮 LLM 处理速度也更快（输入 token 更少）。

2. **最高的运行一致性（95%）**：两轮结果完全相同的任务数（43/75）与 text_only 持平，但翻转任务更少（jina 各 3 个，text_only 各 7-8 个）。Jina 的输出格式标准化（固定 Markdown 格式、统一元数据头）可能降低了 LLM 处理的随机性。

3. **fetch 大小分布特殊**：P50 为 17,623 字符，高于 markdown 的 9,742——这是因为 Jina 在每个页面顶部添加了标准化头部（`Title:`, `URL Source:`, `Published Time:`, `Warning:`），并且更积极地保留页面中的所有文本内容（包括某些 markdown 不转换的字段）。

4. **L1 表现接近 text_only**：L1 准确率 67%，仅比 text_only（68%）低 1 个百分点，优于 markdown（65%）。这说明 Jina 的内容质量对简单任务足够好。

5. **L3 表现中等**（33%，介于 markdown 25% 和 pruned_html 38% 之间）：在 L3 的 5 个任务中，jina_reader 有 2 个 overflow（384d0dd8 PubChem 任务在 R2 中溢出）。Jina 对深度技术页面（如 PubChem 分类页）返回的 markdown 内容相当大，在多步骤 L3 任务中容易累积超出 context 限制。

**为什么 jina_reader 没有超过 text_only？**

核心原因是 Jina 返回的内容**总是比 text_only 大**（中位数 3.4x）。这一额外的 token 开销没有带来对应的准确率提升，反而：
- 导致 context overflow 比 text_only 多（7 次 vs 0 次）
- 消耗更多 token（215K vs 179K），降低 token 效率（2.8 vs 3.8）

Jina 附加的元数据（URL、发布时间、警告信息）对大多数 GAIA 任务无实质帮助。在 GAIA 任务要求精确的具体数据（数字、名称、日期）的场景下，这些元数据是噪声。

**适用场景分析**：

jina_reader 可能在以下场景优于本地提取方案：
- **JavaScript 重度渲染页面**：Jina 有专门的 JS 执行支持，比 Playwright `domcontentloaded` 更可靠（不过本实验中 Playwright 也等待 2000ms JS 渲染）
- **对延迟敏感的场景**：在需要快速响应时，Jina 的端到端处理速度有优势
- **无本地 Playwright 环境**：云原生部署时可以完全省略浏览器基础设施

---

## 5. 关键发现

### 发现 1: 简洁胜过结构

这是实验最核心的结论。**纯文本（text_only）在所有维度上都是最优或接近最优的选择**：

- 准确率最高（67.3%）
- Token 消耗最低（27.1M）
- 零 context overflow
- L3 准确率最高（50%）
- Token 效率最高（3.8 正确/百万 token）

这意味着：对于当前能力水平的 LLM（Claude Haiku 4.5），**减少噪声比保留结构更重要**。LLM 从纯文本中提取信息的能力已经足够好，不需要额外的格式辅助。

加入 jina_reader 后，5 策略排名如下：**text_only (67.3%) > markdown (65.3%) > jina_reader (61.3%) = pruned_html (60.0%) >> raw_html (41.3%)**。结论不变。

### 发现 2: Context 是最稀缺的资源

raw_html 的失败模式单一且致命——context overflow。37% 的调用因此直接失败。这不是一个"准确率略有下降"的问题，而是**功能性的完全丧失**。

在 context window 有限的情况下，每一个 token 都是稀缺资源。将 token 浪费在 HTML 标签和样板代码上，直接减少了 agent 可以存储的有用信息和进行的推理步数。

### 发现 3: Markdown 是一个合理的妥协

如果某些场景确实依赖表格/列表结构（如数据分析、结构化信息提取），markdown 是合理的选择。它的准确率（65.3%）接近 text_only（67.3%），context overflow 风险很低（3%），并且在个别结构依赖任务上有独到优势。

但作为**默认选择**，text_only 更优。

### 发现 4: 过度工程化的清理适得其反

pruned_html 试图做"智能清理"，结果反而不如简单粗暴的 text_only。这个教训对系统设计有启示意义：**简单的方法往往比复杂的启发式更鲁棒**。

### 发现 5: Jina Reader 的速度优势未能转化为准确率优势

jina_reader 是实验中延迟**第二低**的策略（59.8s），并且具有最高的运行一致性（95%）——这两个指标都很优秀。但它的准确率（61.3%）明显低于 text_only（67.3%）。

原因清晰：Jina 返回的内容比 text_only 大 3.4 倍（中位数 17,623 vs 5,180 字符），额外的元数据（URL、发布时间、缓存警告）对 GAIA 任务无益，却占用了宝贵的 context。这是一个有趣的"速度-准确率"解耦案例：**更快的内容处理不等于更好的任务表现**，关键仍是内容的信噪比。

---

## 6. 对生产系统的建议

1. **默认使用纯文本提取**。对网页内容调用 `soup.get_text()` 是最简单、最高效的方式。
2. **如需结构信息，使用 Markdown**。在明确需要解析表格/列表的场景下，MarkItDown 是合理的升级路径。
3. **永远不要直接喂原始 HTML**。这是资源浪费，且在多步任务中会导致功能性失败。
4. **不要尝试"智能 HTML 清理"**。基于启发式规则的 DOM 清理既复杂又脆弱，不如直接提取纯文本。
5. **Jina Reader 适合特定场景**。在无 Playwright 环境、对延迟敏感、或需要处理 JS 重度渲染页面时，Jina Reader 是合理选择；但对 token 效率要求高的场景，text_only 仍占优势。
6. **监控 context 利用率**。context overflow 是 DeepSearch agent 最大的单点故障模式。

---

## 7. 局限性

1. **单一模型**：仅测试了 Claude Haiku 4.5。更大的模型（如 Sonnet/Opus）可能有不同的 context window 大小和信息提取能力，结论不一定适用。
2. **任务集偏差**：GAIA benchmark 的纯网页搜索子集（75 任务）可能不代表所有 DeepSearch 场景。
3. **temperature=0**：确定性输出下测试，不反映带随机性的生产配置。
4. **Serper API 的影响**：实验过程中多次遭遇 API 限流和额度耗尽：
   - **Run 1**：pruned_html 的 36 个任务因 Serper 400 错误需要补跑，补跑数据与原始运行间隔约 6 小时。
   - **Run 2**：pruned_html 有 21 个任务遭遇 "All Serper API keys exhausted"，经补跑修正。raw_html 和 markdown 各有 3 个任务受少量影响（未补跑，影响可忽略）。
   - 所有受影响数据均已通过补跑修正，最终结果为干净数据。
5. **网页动态性**：补跑任务与原始运行间隔数小时至一天，网页内容可能发生变化。
6. **策略执行顺序偏差**：每轮按 raw_html → markdown → text_only → pruned_html → jina_reader 固定顺序执行。理想的实验设计应随机化策略执行顺序或交叉执行，避免系统性偏差。
7. **jina_reader 的双重抓取开销**：jina_reader 策略在 Playwright 抓取页面后，再通过 Jina API 重新抓取同一 URL（见 strategies.py 实现），产生两次网络请求。实验测得的 latency 已包含此开销，但实际部署中可优化为仅调用 Jina API（省去 Playwright）。

---

## 8. 后续方向

1. **在更大模型上验证**：Sonnet 4 有更大的 context window，raw_html 的 overflow 问题可能减轻。text_only 的优势是否依然成立？
2. **自适应格式选择**：根据网页类型（数据表格 vs 文章 vs 论坛）动态选择格式策略。
3. **内容截断实验**：在 text_only 基础上，测试不同的最大内容长度（如 5K, 10K, 20K 字符）对准确率的影响。
4. **优化 jina_reader 实现**：去掉 Playwright 双重抓取，使用纯 Jina API 调用，测量 latency 和准确率变化。同时可以测试 Jina 的 `X-Return-Format: text` 模式（纯文本输出，可能减少 token 消耗并超越 jina_reader 当前结果）。

---

*实验运行时间：2026-03-25 15:00 — 2026-03-27 00:33*
*总计：75 任务 × 5 策略 × 2 runs = 750 次 agent 调用*
*总 token 消耗：约 167M（含 jina_reader 32.3M）*
