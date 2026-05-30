# 014 多 Agent 实验 — 深化讨论存档

**日期**：2026-05-21
**状态**：讨论中，未锁定。后续将接续讨论。

---

## 1. 调研背景

本次讨论基于三路并行调研：

### 1.1 Claude Code 2.1.88 多 agent 源码
源码位置：本地 clone 的 `claude-code-analysis` 仓库

**架构**：三种多 agent 模式并存
1. 普通 Subagent（含 fork）—— `AgentTool` 派出一次性 worker
2. Coordinator Mode —— 主线程身份重写为 orchestrator
3. Swarm / Teammates —— team + lead + teammates + 共享 mailbox + 共享 task list

**关键代码位置**：
| 关注点 | 文件 | 位置 |
|---|---|---|
| 多 agent 入口路由 | `src/tools/AgentTool/AgentTool.tsx` | call() L266-335 |
| Teammate 拒绝嵌套 | 同上 | L272, L278-279 |
| 普通 subagent 内核 | `src/tools/AgentTool/runAgent.ts` | 973 行 |
| Fork subagent | `src/tools/AgentTool/forkSubagent.ts` | `buildForkedMessages` L96-, 注释 L23-58 |
| Coordinator 模式 | `src/coordinator/coordinatorMode.ts` | `isCoordinatorMode()` L36 |
| `<task-notification>` 协议 | 同上 | L144-159 |
| Teammate spawn | `src/tools/shared/spawnMultiAgent.ts` | `spawnTeammate()` |
| 同进程 teammate | `src/utils/swarm/spawnInProcess.ts` | `spawnInProcessTeammate()` |
| Mailbox 文件通信 | `src/utils/teammateMailbox.ts` | `writeToMailbox` / `readUnreadMessages` |
| SendMessage 路由 | `src/tools/SendMessageTool/SendMessageTool.ts` | L41 / L161-173 |
| Inbox 轮询 | `src/hooks/useInboxPoller.ts` | - |
| 权限桥 | `src/utils/swarm/leaderPermissionBridge.ts` | - |
| Team / 任务平面 | `src/tools/TeamCreateTool/TeamCreateTool.ts` 等 | - |

**核心设计决策**：
- **Context 二分**：fork 复用父端**已渲染 system prompt 字节**（核心动机：prompt cache 命中，不是上下文共享）；普通 subagent 则是**全新隔离 context**
- **结果回流：结构化协议**：`<task-notification>` 四元组（status/summary/result/usage）
- **拓扑严格约束**：teammate 不能嵌套，in-process teammate 不能后台
- **协作工具是 runtime contract**：teammate 工具池被强行注入 SendMessage / TeamCreate / TaskCreate 等
- **权限桥双轨**：worker 无 UI，请求回流到 leader 的 ToolUseConfirmQueue + mailbox 容灾
- **编排是 hierarchical 而非 P2P**：权限和任务都汇到 leader

### 1.2 014 现状
- 仅有 `plan.md`（2026-05-06 草稿），未锁定
- 原计划：5 pattern × 5 task × 双轨 13 组 ≈ 9750 runs / 1B+ tokens
- 三个核心阻塞：
  1. Agent Teams 无程序化 spawn API（CLI/interactive only）
  2. mailbox / task_list 是否能被 `disallowedTools` 硬隔离未确认
  3. 规模太大、预算未拍板
- 三条核心假设：H1 主场胜出 / H2 错配损失 / H3 Claude Code Native > sum of parts

### 1.3 网络调研核心收敛
**两极对立**：
- **Anthropic**（research system 博客）：Opus 4 lead + Sonnet 4 subagents 比单 agent **高 90.2%**；但 token 多 **15×**；BrowseComp 上 token 单变量解释 **80% variance**
- **Cognition**（Walden Yan, *Don't Build Multi-Agents*）：写代码场景多 agent 系统性失败。两条原则：(1) Share full traces, not just messages; (2) Actions carry implicit decisions, conflicting decisions = bad results。Flappy Bird 例子。

**LangChain 调和**（Harrison Chase）：
- read-heavy + 高度可并行 → multi-agent 胜
- write-heavy + 高耦合 → single-thread 胜
- "read actions are inherently more parallelizable than write actions"
- Anthropic 自己的 final synthesis 也收敛到一个 agent

**MASFT 失败学**（Cemri et al., arXiv 2503.13657）：
- 14 种失败模式 → 3 大类（FC1 Spec & Design / FC2 Inter-Agent Misalignment / FC3 Verification & Termination）
- ChatDev 正确率 25%；tactical fix 只能拉到 40.6%
- **结构性问题不能靠 prompt 调优解决**

**支持多 agent 实证**：
- Multi-Agent Debate（Du et al. 2023）—— math/strategic reasoning factuality 提升
- Agent Forest / More Agents Is All You Need（Li et al., arXiv 2402.05120, TMLR 2024）—— sampling-and-voting，难度越高收益越大
- AgentVerse、MetaGPT —— 角色分工 SOP

**主要参考链接**：
- Anthropic *Building Effective Agents*：anthropic.com/engineering/building-effective-agents
- Anthropic *How we built our multi-agent research system*：anthropic.com/engineering/built-multi-agent-research-system
- Cognition *Don't Build Multi-Agents*：cognition.ai/blog/dont-build-multi-agents
- LangChain *How and When to Build Multi-Agent Systems*：langchain.com/blog/how-and-when-to-build-multi-agent-systems
- MASFT：arXiv:2503.13657
- Multi-Agent Debate：arXiv:2305.14325
- Agent Forest：arXiv:2402.05120
- MetaGPT：arXiv:2308.00352
- AgentVerse：arXiv:2308.10848

---

## 2. 对 014 原设计的核心担忧

1. **复现博客 vs 验证非平凡假设**：原 plan 的"5 pattern × 主场任务"本质上等于给 Anthropic 博客背书
2. **Agent Teams spawn API 缺失**是红旗——要么改源码（破坏代表性），要么放弃
3. **规模 9750 runs 不可持续**——但 MASFT 显示结构性问题不靠 prompt 调，少量精心对照 > 海量
4. **真正缺失的实验**：所有人都在比较"哪个 pattern 更好"，**没人系统隔离 multi-agent 增益的来源**——这是最有价值、最少人做的方向

---

## 3. 选定方向：增益归因实验（用户已选 A）

### 3.1 核心问题
Anthropic 称 orchestrator-worker 比 single agent 高 90.2%，token 解释 80% 方差。**把 token 给够，single 还差多少？这部分残差才是真正的多 agent 红利。**

### 3.2 四个可隔离因子

| 因子 | 含义 | 隔离方法 |
|---|---|---|
| F1 Token 预算 | 多 agent 烧 ~15× token | 给 single agent 等量 token 预算 |
| F2 Context 隔离 | subagent 起手干净，无前序污染 | single agent 周期性 reset + 摘要 |
| F3 探索多样性 | 并行 N 路独立搜索 | single agent 串行做 N 个分支，每分支 reset |
| F4 协调红利（残差） | orchestrator 动态分配/交叉验证 | F1-F3 拉平后剩下的差距 |

### 3.3 6 个对照条件

```
S0      vanilla single agent，默认 token 上限
S+T     single agent，token 上限 = MA 总用量（隔离 F1）
S+T+R   S+T + 周期性 context 重置/摘要（叠加 F2）
S+T+R+P single agent 串行跑 N 个 sub-question，每个 reset（叠加 F3）
MA-seq  orchestrator + N 个 subagent，但顺序执行（去掉 wall-time 收益）
MA      orchestrator + N 个 subagent，并行执行（Anthropic 配置）
```

归因公式：
- gap(S+T, S0) = token 效应
- gap(S+T+R, S+T) = context 隔离效应
- gap(S+T+R+P, S+T+R) = 多路探索效应
- gap(MA-seq, S+T+R+P) = **协调/编排效应（关键残差）**
- gap(MA, MA-seq) ≈ wall-time（对正确率应 ≈0）

### 3.4 Benchmark 选型
必须 read-heavy + breadth-first，否则分解无意义：
1. **FanOutQA**（首选）—— 天生 fan-out 多源 QA，静态文档
2. **FRAMES** —— multi-doc retrieval QA，DeepMind
3. BrowseComp 子集（最接近 Anthropic eval 但需活 web，工程脏）

**建议**：FanOutQA + FRAMES 子集，各 50 题共 100 题，本地静态 index。

### 3.5 工程难点 & 关键决策（待讨论）
1. "等量 token" 定义：等 output / 等 total / 等 cost？建议 **等 total**
2. **F3 "串行 N 路"实现**最有风险——需要 hook 强制 agent 拆题→逐个 reset→综合
3. 拆题 prompt 公平性：MA orchestrator 与 S+T+R+P 看到的拆题 prompt 字面相同
4. N 选取：建议固定 N=4 起步，pilot 后再扫
5. 评分：用 FanOutQA / FRAMES 官方 metric

### 3.6 规模估算
- 6 条件 × 100 题 × 3 seed = **1800 runs**
- ~150-200M tokens；Sonnet 4.6 约 $300-500
- Pilot：10 题 × 6 条件 × 1 seed = 60 runs（必做）

### 3.7 实验卖点
- **任何结果都有信息量**：
  - F4 残差 ≈ 0 → 强支持 Cognition："multi-agent 是 token 套壳"
  - F4 残差大 → 量化 Anthropic 的协调红利
  - F1 占主导 → 关键事实：multi-agent 主要是花钱买正确率
- **没人系统做过这个分解**——目前都是 architecture-vs-architecture 黑箱对比

### 3.8 与 014 的关系
建议**新建 015_multi_agent_attribution**，014 的 plan.md 保留为更宽"未来工作"。

---

## 4. 待续讨论的关键决策点

1. F3 手写串行 orchestrator 的实现细节（最有风险）
2. "等量 token" 到底等什么
3. Benchmark 最终选谁
4. 是否新建 015 vs 在 014 内部演进
