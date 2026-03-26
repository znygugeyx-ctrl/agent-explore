# 实验 007: 网页内容格式对 DeepSearch Agent 的影响

## 背景

DeepSearch agent 通过抓取网页并将内容注入 LLM context 来回答问题。不同系统对网页内容的处理方式各异：原始 HTML、Markdown、纯文本、清理后的 HTML。目前没有系统性对比研究评估格式选择对回答质量和 token 消耗的影响。

## 假设

- **H1**: Markdown 在准确率/token 效率上达到最优平衡（保留结构，去除样板代码）
- **H2**: 原始 HTML 消耗远超其他格式的 token，但不带来准确率提升
- **H3**: 纯文本格式在依赖表格/列表的问题上准确率下降
- **H4**: 在多跳查询中，原始 HTML 导致 context 膨胀和推理退化

## 实验设计

### 策略（4 种）

| 策略 | 实现方式 | 描述 |
|------|---------|------|
| `raw_html` | 直接返回 | 控制组，agent 接收完整 HTML |
| `markdown` | MarkItDown | HTML → Markdown 转换 |
| `text_only` | BeautifulSoup | 提取可见文本，不保留结构 |
| `pruned_html` | BeautifulSoup | 移除 script/style/nav/广告，保留语义标签 |

机制：通过 `after_tool_exec` hook 拦截 `fetch_page` 返回的原始 HTML，按策略转换后再交给 agent。

### 任务集

来源：GAIA benchmark validation set（HuggingFace `gaia-benchmark/GAIA`）

**筛选条件（严格）：**
- 无文件附件（排除 PDF、图片等需要本地文件处理的任务）
- 无特殊工具需求（排除 calculator、image、video、audio、code、excel、python、ocr、vision）
- 仅保留纯网页搜索 + 抓取可完成的任务

**筛选结果：**

| 级别 | 原始数量 | 筛选后 | 平均步骤数 |
|------|---------|--------|-----------|
| L1 | 53 | 33 | 5.1 |
| L2 | 86 | 37 | 7.9 |
| L3 | 26 | 5 | 12.6 |
| **合计** | **165** | **75** | - |

排除原因分布：文件附件(38)、calculator(25)、image(13)、video(6)、OCR/vision(4)、其他(4)

### 模型与工具

- **LLM**: Claude Sonnet 4 (`us.anthropic.claude-sonnet-4-20250514-v1:0`) via AWS Bedrock
- **搜索**: Serper API（Google 搜索）
- **网页抓取**: Playwright headless Chromium（本地）
- **验证**: GAIA 标准（精确匹配 + LLM judge 兜底）

### 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| max_turns | 30 | L3 任务需要更多步骤（Phase 1 的 15 不够） |
| concurrency | 2 | 并行任务数，遇限流自动退避 |
| runs | 2 | 每策略独立运行 2 次 |
| temperature | 0.0 | 确定性输出 |
| max_tokens | 4096 | 每次 LLM 响应上限 |

### 错误处理

- **ThrottlingException**: 可重试，退避间隔 10s/30s/60s
- **ValidationException (input too long)**: 不重试，记录为策略缺陷，**计入准确率（error = wrong）**
- **Playwright 超时**: 单页 30s + JS 渲染 2s，总超时 180s

## Phase 1 结果摘要

Phase 1（9 任务 × 4 策略 × 1 run）用于验证基础设施，结果：

| 策略 | 准确率 | 平均延迟 | 平均 Input Tok | Context 溢出 |
|------|--------|---------|---------------|-------------|
| text_only | **66.7%** | 61.5s | 120,381 | 0 |
| markdown | 55.6% | 54.5s | 131,864 | 2 |
| pruned_html | 55.6% | 98.0s | 232,910 | 0 |
| raw_html | 22.2% | 100.8s | 296,830 | 4 |

关键发现：
1. text_only 是唯一 0 context 溢出的策略，准确率最高
2. raw_html 有 44% 的任务因 context 溢出失败
3. L3 任务普遍困难，仅 markdown 解答了 1 个 L3

## Phase 2 运行

### 命令

```bash
SERPER_API_KEY="<key>" \
python3 -m experiments.007_content_format.run \
    --tasks experiments/007_content_format/tasks_phase2.jsonl \
    --runs 2 \
    --strategies raw_html markdown text_only pruned_html \
    --max-turns 30 \
    --concurrency 2
```

### 资源预估

- 总调用次数: 75 × 4 × 2 = **600 次 agent 调用**
- 预计耗时: concurrency=2 下约 **5-8 小时**
- Serper API 消耗: 约 3,000-5,000 次搜索查询
- Bedrock token 消耗: 约 50M-100M input tokens

### Observer

所有数据统一写入 `observer/data/exp_007_phase2/`，task_id 格式：`{strategy}_r{run_id}_{task_id}`

## 分析维度

1. **按策略对比**: 准确率、token 效率、延迟
2. **按级别对比**: L1/L2/L3 各策略表现
3. **Context 溢出率**: 各策略有多少任务因 input too long 失败
4. **Token 效率**: 准确率 / 每百万 token
5. **Fetch 大小分布**: 各策略的内容压缩比
6. **失败模式分析**: 哪些任务在所有策略中都失败（任务本身难度 vs 格式影响）
