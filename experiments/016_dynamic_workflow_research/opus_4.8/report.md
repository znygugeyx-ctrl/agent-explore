# Claude Code 动态工作流（Dynamic Workflows）调研报告

> 研究规模：6 个检索角度 → 19 个来源 → 92 条声明 → 对置信度最高的 25 条做 3 票对抗式验证（23 条确认 / 2 条被否决）。核心事实全部来自 Anthropic 官方一手来源（code.claude.com 文档、工程博客、GitHub CHANGELOG），暂无第三方独立佐证。

---

## 一、它是什么

**动态工作流就是一段由 Claude 编写、用来大规模编排 subagent 的 JavaScript 脚本，由一个独立运行时（runtime）在后台执行，而你的交互会话保持响应。**

官方文档原文：
> "A dynamic workflow is a JavaScript script that orchestrates subagents at scale. Claude writes the script for the task you describe, and a runtime executes it in the background while your session stays responsive."

- 运行时在**与对话隔离的环境**中执行脚本（"separate from your conversation"）。
- 规模可达**每次运行数十到数百个 agent**（"Dozens to hundreds of agents per run"）。
- CHANGELOG v2.1.154 印证："Introducing dynamic workflows: ask Claude to create a workflow and it orchestrates work across tens to hundreds of agents in the background."

**可用性（research preview）：**
- 需要 **Claude Code v2.1.154 或更高版本**；
- 当前为 **research preview**；
- 覆盖所有付费计划 + Anthropic API + Amazon Bedrock + Google Cloud Vertex AI + Microsoft Foundry；
- Pro 计划需在 `/config` 的 "Dynamic workflows" 一行手动开启。

来源：`code.claude.com/docs/en/workflows`、`/agents`，CHANGELOG（置信度：高，3-0）

---

## 二、核心架构思想（最关键的一点）

**确定性控制流（循环、分支/条件、扇出 fan-out、中间结果）全部活在脚本本身的变量里，所以 Claude 的上下文窗口只装最终答案。**

文档原文：
> "A workflow script holds the loop, the branching, and the intermediate results itself, so Claude's context holds only the final answer."
> "Intermediate results stay in script variables instead of landing in Claude's context."

这就是它与 subagent/skill 的本质区别——一张官方对比表说得很清楚：

| 维度 | 动态工作流 | Subagents / Skills |
|---|---|---|
| **谁决定下一步运行什么** | 脚本 | Claude，逐回合（turn by turn）决定 |
| **中间结果存在哪里** | 脚本变量 | Claude 的上下文窗口 |

一句话总结官方的定位：**"A workflow moves the plan into code"**（把计划从 Claude 的逐回合判断搬进代码）。这正是它能扩展到数百 agent 而不撑爆上下文的根本原因。

来源：`/docs/en/workflows`（置信度：高，3-0）

---

## 三、在三种协作模式中的位置

Claude Code 有三种多 agent 协作方式，区别在于"谁持有计划"：

| 模式 | 谁持有计划 | 典型场景 |
|---|---|---|
| **动态工作流** | **脚本**持有计划 | 任务太大、无法逐回合协调，或需要多轮交叉验证 |
| **Subagents** | Claude 在**一个对话内**委派并收集结果 | 单次会话内的并行调查 |
| **Agent Teams**（实验性，默认关闭） | Claude **规划、分配、监督**一组对等 worker | 多个独立 Claude 实例互相通信、共享任务清单 |

官方 "Choose an approach" 原文：
> "A script holds the plan instead of Claude's turn-by-turn judgment: dynamic workflows / Claude delegates and collects results inside one conversation: subagents / Claude plans, assigns, and supervises a group of workers: agent teams."

来源：`/docs/en/agents`、`/workflows`（置信度：高，3-0）

---

## 四、怎么用

**两种入口：**
1. **运行内置工作流**，例如 `/deep-research`（本报告就是用它跑出来的）；
2. **让 Claude 为你的任务现写一个工作流并保存**。

**监控：** 随时运行 `/workflows`
- 列出正在运行和已完成的 run；
- 显示每个 run 当前所处的**阶段（phase）**；
- 显示每阶段的 **agent 数量、token 总量、已用时长**。

**对抗式验证能力：** 工作流可以让**互相独立的 agent 对彼此的发现做对抗式审查**，"so you get a more trustworthy result than a single pass"（比单次输出更可信）。

**作为后台进程的一等公民：**
- 正在运行的工作流算作 "active work"，会让后台会话保持存活（与 subagent、monitor、后台 shell 命令并列）；
- 它会阻止 left-arrow 后台快捷键，提示 "N background task(s) running"；
- 可用 `/tasks` 查看，`/bg` 确认放弃；
- 在工具层暴露为内置 **`Workflow` 工具**，与 `Agent`、`Monitor` 平级——"Runs a dynamic workflow: a script that orchestrates many subagents in the background and returns one consolidated result"。

来源：`/docs/en/agents`、`/workflows`、`/agent-view`、`/tools-reference`（置信度：高，3-0）

---

## 五、实现原理

### 1. 运行时的硬性限制（已文档化）

| 限制 | 数值 | 目的 |
|---|---|---|
| 并发 agent 数 | **最多 16 个**（CPU 核数少的机器更少） | 限制本地资源占用 |
| 单次运行总 agent 数 | **1,000 个** | 防止失控循环（runaway loops） |

来源：`/docs/en/workflows` "Behavior and limits" 表（置信度：高，3-0）

### 2. 底层委派机制：Subagents

工作流编排的底层单元就是 subagent：
- Claude 根据请求中的任务描述、subagent 配置的 `description` 字段和当前上下文**自动委派**；也可通过自然语言、`@-mention`、或 `--agent` flag 显式调用；
- 每个 subagent 跑在**独立的上下文窗口**里，主 agent 只收到摘要；
- **subagent 不能再生成 subagent**（无嵌套委派，"This prevents infinite nesting"）——所以扇出靠主对话并行生成多个 subagent 再综合，串行流程靠链式调用；
- 当一个 agent 以主线程身份运行（`claude --agent`）时，用 **`Agent` 工具**生成 subagent（v2.1.63 起由 `Task` 改名，`Task(...)` 仍作为别名保留），可用 `Agent(agent_type)` 白名单语法限制可生成的类型。

来源：`/docs/en/sub-agents`（置信度：高，3-0）

### 3. 概念基础：Orchestrator-Worker 模式

Claude 编排多 subagent 的概念基础是 **orchestrator-worker（编排者-工作者）模式**：

> "In the orchestrator-workers workflow, a central LLM dynamically breaks down tasks, delegates them to worker LLMs, and synthesizes their results."（*Building Effective Agents*, 2024-12）

这正是 Anthropic 多 agent **Research 系统**背后的架构：
> "Our Research system uses a multi-agent architecture with an orchestrator-worker pattern, where a lead agent coordinates the process while delegating to specialized subagents that operate in parallel."（2025-06）

该系统的动态、迭代特征：
- lead agent **并行**（而非串行）启动 **3-5 个 subagent**，每个 subagent 再并行用 3+ 个工具——"cut research time by up to 90%"；
- lead 综合结果后**在运行时决定**是否再生成更多 subagent 或调整策略，形成迭代循环；
- "You can't hardcode a fixed path for exploring complex topics, as the process is inherently dynamic and path-dependent."（无法为复杂任务硬编码固定路径，过程天然是动态、路径依赖的）。

来源：`anthropic.com/engineering/building-effective-agents`、`/multi-agent-research-system`、`/docs/en/sub-agents`（置信度：高）

---

## 六、重要边界与被否决的说法（诚实声明）

**官方未公开底层控制流原语的实现细节。** 经验证否决了一条声明（1-2 票）：CHANGELOG 与文档只描述"编排"和"限制"，**并未发布**循环/条件/扇出原语的底层实现。文档讲的是"做什么"和"边界"，不是"怎么实现的源码级细节"。

**另一条被否决的说法（0-3 票）：** 不能简单地把动态工作流的框架等同于 *Building Effective Agents* 里"workflows（确定性代码路径）vs agents（LLM 自主导向）"那个二分法——那篇是通用模式目录，本身并未点名 Claude Code 或动态工作流。

**注意一个常见混淆：** 文档里那套**带依赖的共享任务清单、三态（pending/in progress/completed）、文件锁防竞态、四组件（team lead / teammates / task list / mailbox）、状态存于 `~/.claude/teams/` 和 `~/.claude/tasks/`** ——这些是 **Agent Teams** 的实现机制，**不是**动态工作流的。动态工作流的确定性来自 JS 脚本自己的循环/分支变量。

**单一厂商来源：** 所有核心事实仅来自 Anthropic 自家来源，无第三方独立验证。且功能处于 research preview、绑定具体版本号，16/1,000 上限、`/config` 开关等都可能变动。

---

## 七、尚未解答的问题

1. **脚本的具体 API 表面**：Claude 到底调用哪些函数/原语来生成 agent、扇出、循环、分支？这套 API 是否有超出"一段 JavaScript 脚本"这种高层描述的文档？
2. **失败处理**：运行时如何处理失败、重试、部分结果，以及中途撞到 1,000-agent 上限时是优雅降级还是硬中断？工作流能否暂停/恢复、能否确定性地保存并重跑？
3. **与 Agent Teams 的实战取舍**：同一个大任务，何时该选工作流的"脚本持有计划"，何时该选 Agent Teams 的"共享任务清单自协调"？
4. **真实成本与延迟**：生产中动态工作流的 token 成本和延迟特征如何？（Research 系统博客提到约 15 倍 token 成本、最多 90% 时间缩减——这些数字是否适用于动态工作流？）

---

## 主要来源（一手）

- `code.claude.com/docs/en/workflows`（主文档，5 条声明）
- `code.claude.com/docs/en/agents`、`/sub-agents`、`/agent-view`、`/agent-teams`、`/tools-reference`
- `github.com/anthropics/claude-code/blob/main/CHANGELOG.md`（v2.1.154）
- `anthropic.com/engineering/building-effective-agents`
- `anthropic.com/engineering/multi-agent-research-system`
- `claude.com/blog/introducing-dynamic-workflows-in-claude-code`

---

*报告生成自 deep-research 工作流 run `wf_c176b43e-bd5`：102 个 agent、约 3M token、约 9 分钟。*
