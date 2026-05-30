# Multi-agent 方案对比

上一篇文章分析了Claude Code中两种multi agent方式的实现：Coordinator模式 和 Swarm模式，核心区别是agent的组织形式，前者是分支型，后者是星型。问题是：不同架构在不同任务上到底会不会带来收益？这一章将基于Claude Code，分别测试在 “真实工作场景”，“金融场景”，“游戏场景”下，single-agent, Coordinator模式以及Swarm模式的真实表现。

# 实验设计

## Multi-agent架构

对比三类agent架构：

- **Single Agent (single):** 禁用Claude Code的Subagent工具以及Agent teams工具，让Agent靠调用 “普通工具” 产生答案。所有 observation 都在单一 context 内累积。
- **Coordinator模式 (verify)**：主Agent可以调用"普通工具" + "Agent工具"，自行决定由自己回答还是调用一个或者多个"Worker sub-agent"回答。关键约束：主Agent在产出最终答案前，必须调用 "Verifier Sub-agent" 验证答案，循环直到验证通过或达到3轮上限。
- **Swarm模式 (swarm)**：主Agent通过 TeamCreate + Agent 派出 2 个有专长的 teammate：**planner + executor**，模拟人类团队协作：先规划再执行的分工。

主agent和subagent都统一使用claude-opus-4-7-1m模型。

## 测试集

在三个测试集中，每个测试集又分为 easy, medium, hard 三个难度，如下：

- **WorkBench** (https://github.com/olly-styles/WorkBench)：**这个测试集主要关注Agent在真实工作环境下的执行准确度**，Agent需要理解用户问题，实际调用**5类MCP工具** （日历，邮件，数据分析，项目管理，客户关系）去操作sandbox中的模拟数据库，执行完毕后导出sandbox state json，与正确答案进行严格匹配。这里的难度主要是靠 “需要调用的工具类别” + “需要调用的工具次数” 决定。
- **FinanceBench** (https://github.com/patronus-ai/financebench): 这是一个 “基于 SEC 10-K/10-Q 财报” 的金融问答测试集，agent需要检索文档定位数字，然后输出短答案。**这个测试集主要关注的是Agent的检索能力，任务可并行**。文档库由大约168个页面组成。Agent需要操作5个工具去查询文档获取答案：list_filings用于列出所有filings，search_filings按照年份公司过滤，open_filing查看filings下的页面，read_page读取，search_in_filing在页面下搜索。最后将Agent输出和真实答案进行对比。同样分三种难度，靠跨越的“期数” 和 执行的计算复杂度区分。
- **PlanCraft** (https://github.com/gautierdag/plancraft): 这是一个模拟”我的世界”合成任务的测试集，给定一个初始状态（背包里的一堆物品），Agent需要通过 move/smelt 工具逐步合成目标物品。**这是一个强时序性的任务，前面的动作会影响后续的动作，Agent需要有从反馈中学习的能力**。Agent有5个工具：get_target查看目标物品，get_inventory查看当前状态，move移动物品，smelt合成物品，stop标记完成。三级难度，通过需要合成的中间产物的多少区分难度。

对以上三个测试集，每个难度类型选取10题，每个类别总共30个题目。在三个agent架构上测试，总的任务执行次数是 90 * 3 = 270。

# 实验结果与分析

## 主要实验结果

| Agent 框架 | WorkBench | FinanceBench | PlanCraft |     合计 |
| ---------- | --------: | -----------: | --------: | -------: |
| **Single** |       83% |          70% |       90% |  **81%** |
| **Swarm**  |       70% |          67% |       53% |      63% |
| **Verify** |       83% |          70% |       83% |      79% |

三个架构整体表现：**Single > Verify > Swarm**，Single Agent在所有测试集上取得了最好成绩。Verify Agent的模式在 WorkBench 和 FinanceBench 上与 Single 成绩相同，在PlanCraft下比single agent低7%。而Swarm模式则显著低于其他模式。

最值得分析的是在PlanCraft这个测试集上，这里的方差最大。首先，仔细分析三种模式的失败case，发现以下问题，single失败三个case是真正遇到了hard的问题，无法解出来。而Verify模式存在 “**多Agent协作问题**” 导致的副作用，失败率更高。

具体来讲，根据失败的case，存在以下两类协作失效：

- **主Agent没有按照Verify结果修复**：以VAL0581为例，主Agent最后制造出了 2 个 nether_bricks 块和 4 个散 nether_brick，但没合成出最终的 slab。Verify成功的发现并指出了这个问题，但是主Agent回复：“**The session was already stopped. Task failed — produced 2 nether_bricks blocks but ran out of steps before crafting third block and the slab. ANSWER=done**”。也就是主Agent过早的放弃了。当然这里可能和提示词有关，但也侧面反映了多Agent协作的困难点。
- **信息传递有损 + Verify过度思考**：VAL0262 (target=hay_block) 1 步可解，需要把 9 wheat 摆满 3×3 grid。Single 按顺序将 wheat 放到 slot 1→9，中途虽然意外触发 bread 配方但完全没注意输出槽，最终 grid 满后模拟器自动把输出覆盖为 hay_block，成功收尾。**Verify** 主 Agent 走到 step 3 时"看到了"输出槽里的 bread 并自我反思"crafted bread by mistake, consuming 3 wheat"，多走一步把 bread 从输出槽移走：这个"清理"动作恰好让模拟器永久结算了 bread 配方，3 wheat 真的被消耗，剩下 6 wheat 不够 9，任务变得不可逆。**verifier 独立检查 inventory 后正确回复 VERIFY_OK 同意"现状无解"**，主 Agent 接受结论主 Agent 的"过度反思",它把模拟器的中间副产物当真正的错误去清理了。

而对于Swarm架构，失效的主要原因是Agent teams这个架构在当前这个 “**强时序性**” 场景下的失效：

**案例1: VAL0431（target=prismarine_bricks，1 步合成）**

```
msg 1  lead → planner:   "Target: prismarine_bricks. ... Recipe: 9 prismarine_shards filling 3x3 grid"
msg 2  lead → executor:  "Recipe is 2x2 of prismarine_shard → 1 prismarine_bricks."  ← 错的!
msg 3  lead → executor:  "CORRECTION — prismarine_bricks needs full 3x3 (9 shards).
                          If you already started the 2x2 attempt, continue with these additional placements..."
msg 4  lead → planner:   shutdown_request
msg 5  lead → executor:  shutdown_request
```

这是经典的 "信息漂移 + 单向广播" 失败：lead 第一次给 planner 的 plan 是对的（3×3），但 lead 自己把信息传给 executor 时写错成了 2×2，这时候executor 已经按错版本动手了，lead 发 CORRECTION，但 executor 已经把 inventory 弄乱，lead 没有确认 executor 是否收到 CORRECTION 还是已经按错版本走完，发送了 shutdown

**案例2: VAL0577（target=diorite_stairs）**

```
msg 1  lead → planner:   inventory 描述
msg 2  lead → executor:  "Execute these actions in order. After each, observe inventory if needed
                          but trust the plan. ..."  ← "trust the plan" 是协作崩溃的根因
msg 3  lead → planner:   shutdown_request
msg 4  lead → executor:  "Did you execute the plan? Please call get_inventory and DM the result.
                          If diorite_stairs not in inventory, run the action list now."  ← 终于想到要查
msg 5  lead → executor:  shutdown_request
```

lead 在 msg 2 让 executor "trust the plan"，lead主动放弃了 observation。直到 msg 4 才意识到要让 executor 报 inventory，但已经在 msg 3 把 planner shutdown 了，这时没有Agent能根据真实状态重新规划。msg 5 又发了 executor 的 shutdown。

这两个案例说明，在这种强时序性的场景中，Agent teams模式是严重不匹配的，不同agent 成员之间的通信全靠message工具，缺乏统一协调，主Agent又过度依赖于其他agent的结果做判断，错误很容易累积，这实际上也是verify模式失效的一部分原因。多**Agent协作，关键是任务是否可以清晰划分，而不必依赖Agent之间的消息协作**。从实验结果看，至少这三个测试集或多或少都需要Agent有完整连续的上下文，并不适合多Agent模式。

另外，FinanceBench这个金融测试集下，是Swarm与其他两个架构差距最小的，仅仅只落后百分百3。这得益于几点：1，任务是天然可分的，分为 "找文档 → 读数字"两阶段。2， 任务是只读的，没有"中间状态"会被破坏 。

## 按难度分档通过率

| Benchmark        | 难度       | Single |   Swarm |  Verify |
| ---------------- | ---------- | -----: | ------: | ------: |
| **WorkBench**    | Easy       |   100% |     90% |    100% |
|                  | **Medium** |   100% |     80% |     90% |
|                  | Hard       |    50% |     40% |     60% |
| **FinanceBench** | Easy       |    60% |     60% |     60% |
|                  | **Medium** |    60% |     50% |     60% |
|                  | Hard       |    90% |     90% |     90% |
| **PlanCraft**    | Easy       |    80% |     60% |     70% |
|                  | **Medium** |   100% | **30%** | **90%** |
|                  | Hard       |    90% |     70% |     90% |

**Easy / Hard 区间，三种架构表现接近，Medium 区间是三种架构差异最显著的地方**：PlanCraft Medium 上 Single 100% / Verify 90% / Swarm 30%。任务难度刚好落在"single agent 能稳定闭环、但 Swarm 的规划-执行分离会引入错误"的区间。Verify 因为保留了主 agent 的单一行动闭环（仅在 ANSWER 前插入一次独立校验），所以表现接近 Single。

## 平均时间消耗（秒/题）

| Agent 框架 | WorkBench | FinanceBench | PlanCraft |  总平均 |
| ---------- | --------: | -----------: | --------: | ------: |
| **Single** |   **30s** |      **21s** |   **86s** | **46s** |
| **Swarm**  |       73s |          66s |      106s |     82s |
| **Verify** |       55s |          32s |       91s |     60s |

Single耗时最少

## 平均 token 消耗

每题平均，含主 agent + subagent 全部 token：

| Agent 框架 | WorkBench | FinanceBench | PlanCraft | 总平均 |
| ---------- | --------: | -----------: | --------: | -----: |
| **Single** | **224 k** |    **159 k** |     551 k |  311 k |
| **Swarm**  |     318 k |        297 k | **335 k** |  317 k |
| **Verify** |     511 k |        313 k |     749 k |  524 k |

Single 没有 subagent，所有 token 都在主 agent；Swarm 把 planner / executor 两个 teammate 的 token 也累加；Verify 把 verifier subagent 算进来。

Swarm 与 Single 总平均接近（317k vs 311k），但**两者的 token 分布不同**：

- WorkBench / FinanceBench 上，Swarm 的 token 比 Single **多 40%~87%**：一份用户任务被传给 planner、再传给 executor，每次跨 agent 通信都带来上下文重渲染，多 agent 协作本身就有 token overhead。

- PlanCraft 上反而 Swarm 的 token 比 Single **少 39%**（335k vs 551k）：这是任务被提前放弃的副作用，执行被提前切断。

Verify 的 token 最多，因为它在主 agent 完整解完题后， spawn verifier 还需要重新读一次完整状态，上下文被重新注入了一次。

# 总结

从实验结果看，Multi agent的有效性强依赖于任务性质。1，任务越可分，multi agent表现越好。2，只读任务更适合multi agent，不用担心中间状态被破坏。反之，任务时序性越强，依赖的交叉文件越多，multi agent表现越差。总的来说，带sub agent工具的主agent模式是一个比较平衡的框架。
