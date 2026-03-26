# Experiment 007: Web Page Content Format Impact on DeepSearch Agent

## Background

DeepSearch agents fetch web pages and feed their content into the LLM context.
The format of this content varies across production systems: raw HTML, markdown
(via MarkItDown/Jina Reader), plain text, or cleaned HTML. No systematic
comparison exists for how format choice affects answer quality and token cost.

## Hypotheses

- **H1**: Markdown achieves the best accuracy/token trade-off (preserves structure, removes boilerplate)
- **H2**: Raw HTML consumes far more tokens than other formats without accuracy gain
- **H3**: Text-only format degrades accuracy on table/list-dependent questions
- **H4**: In multi-hop queries, raw HTML causes context bloat and reasoning degradation

## Design

- **Strategies**: raw_html, markdown, text_only, pruned_html
- **Mechanism**: `after_tool_exec` hook transforms fetch_page raw HTML per strategy
- **Tasks**: GAIA L1/L2/L3 validation set (strict web-search-only subset, 75 tasks)
- **Model**: Claude Sonnet 4 on AWS Bedrock
- **Search**: Serper API (Google search)
- **Page fetch**: Local Playwright headless browser
- **Runs**: 2 per strategy (independent end-to-end)
- **Verification**: GAIA-style (exact match + LLM judge fallback)

## Metrics

- Accuracy (primary)
- Total tokens consumed
- Number of turns / fetch_page calls
- Content size per fetch (chars)
- Latency per task
