# Claude Code Dynamic Workflows 调研报告

## 1. 官方定义、发布时间、定位

- **定义**：Dynamic workflow 是 **由 Claude 编写的一段 JavaScript 脚本**，由独立于会话的 workflow runtime 在后台执行，用于编排大规模 subagent。
- **发布**：2026 年 5 月底（Week 22, 5/25–5/29），**research preview**，要求 Claude Code **v2.1.154+**，覆盖所有付费计划。
- **定位**：codebase 审计、大规模迁移、cross-checked research——"work too big to coordinate one turn at a time"。
- 来源：`code.claude.com/docs/en/workflows`、`/agents`、`/llms.txt`

## 2. 与 Subagents / Skills 的根本区别

| 维度 | Subagents/Skills | Dynamic Workflows |
|---|---|---|
| 谁决定下一步执行什么 | Claude，逐轮判断 | **脚本**（循环、分支由代码控制） |
| 中间结果存在哪 | Claude 的 context window | **脚本变量**，仅最终答案回 context |
| 执行环境 | 主会话内 | **隔离的 runtime**，后台运行 |
| 能否 spawn 嵌套 | subagents 不能再 spawn subagent | 脚本 spawn 多个 agent |

这是核心创新：**把 plan 从 LLM 的逐轮判断中拿出来，交给确定性脚本**，避免 context 被中间结果污染。

## 3. Runtime 实现机制与硬限制

- **隔离执行**：runtime 在与会话隔离的环境中跑脚本。
- **脚本本身无 I/O 权**：不能直接访问 filesystem/shell——所有读写命令由 spawn 的 agent 完成，脚本只做协调。
- **并发上限 16**（CPU 受限机器更少）；**单 run 总计 1000 个 agent**（防 runaway）；**no mid-run user input**。
- **Resume**：runtime 缓存每个 agent 结果——重启时已完成 agent 返回缓存，剩余 live 跑。但 **resume 仅在同一 Claude Code session 内有效**，退出 Claude Code 后下次会从头开始。

## 4. Hook 与 Context 共享体系（支撑 workflow 的底层）

- Agent SDK 的 lifecycle hook：`PreToolUse / PostToolUse / Stop / SessionStart / SessionEnd / UserPromptSubmit`；Claude Code 额外暴露 **`SubagentStart` / `SubagentStop`**（subagent 内的 Stop 自动转为 SubagentStop）。
- Hook payload 含 **`agent_id` / `agent_type`** 字段以区分 subagent 调用。matcher 支持 `general-purpose / Explore / Plan / 自定义名`。
- **`additionalContext`** 字段：hook 返回字符串后被包成 system reminder 注入对话——`SessionStart/Setup/SubagentStart` 注入到对话开头；mid-session 注入会保存到 transcript，`--continue/--resume` 时直接 replay；`SessionStart` hook 在 resume 时以 `source='resume'` 重跑以刷新 stale context。
- **实验性 `type: "agent"` hook**：spawn 一个带 `Read/Grep/Glob` 的 subagent，在动作前进行验证再返回 decision——这正是 adversarial verify 模式的底层支撑。

## 5. Claude Code 的四种并行机制

| 机制 | 隔离粒度 | 通信 | 能否嵌套 |
|---|---|---|---|
| **Subagents** | 单 session 内 | 仅回主 agent | 否 |
| **Agent view** | 背景独立 session | — | — |
| **Agent teams**（实验性，需 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`） | 每 teammate 独立 context | mailbox 互发消息，task 文件锁认领 | — |
| **Dynamic workflows** | 脚本 + 多个 agent | 脚本变量传递 | 脚本 spawn agent（不再嵌套） |

## 6. 典型使用模式

- **Adversarial verify**：脚本 spawn 多个独立 agent 对 claim 投票（如 deep-research 的 3-vote 机制）。
- **Pipeline**：每个 item 独立穿过多个 stage，无 barrier，wall-clock 等于最慢链。
- **Loop-until-dry**：累加直到 K 轮无新 finding。
- **Multi-modal sweep / Judge panel / Completeness critic**：workflow 文档将 cross-checked research 列为典型用例。
- Quality gate 由 agent-teams 的 `TeammateIdle/TaskCreated/TaskCompleted` hook + exit code 2 实现阻断/反馈。

## 重要 caveat

> 用户问题中提到的 `agent() / parallel() / pipeline() / phase()` 这些**具体函数名在公开 docs 中未直接列出**——文档只用 "the script holds the loop, the branching" 这种抽象描述。这些函数名在 Claude Code 自身的 Workflow tool 工具说明里有详细规范（Workflow 工具描述是这些 API 的权威源），但**未出现在 code.claude.com 的公开 docs 页**。所以脚本 API 的官方公开签名仍待 Anthropic 后续补充。

## 仍未确认

1. Workflow runtime 是否与 Agent SDK 共享 subagent 执行栈与 prompt cache。
2. Resume 限同 session 是产品决策还是技术限制；是否计划跨 session 持久化。
3. 脚本是否在 V8 isolate / worker thread 沙盒。
4. 公开 API 的完整签名（agent/parallel/pipeline/phase 的官方文档形式）。

## 来源

主要来源：`code.claude.com/docs/en/{workflows, agents, sub-agents, agent-teams, agent-view, hooks, agent-sdk/overview}`、`llms.txt`、`github.com/anthropics/claude-code` 仓库 plugins 目录。

调研统计：21 source、102 claim、25 个 claim 经 3-vote 对抗验证全部确认（0 killed）。
