# Experiment 008: MiroThinker-1.7-mini — Results

Generated: 2026-03-28 20:44:51

Model: miromind-ai/MiroThinker-1.7-mini via vLLM (TP=4, EC2 g6e.12xlarge)

## Summary

- Runs: 2, Tasks per run: 9
- **Overall accuracy: 38.9%** (7/18)
- Avg latency: 225.1s
- Avg turns: 20.1
- Avg web_search calls: 15.6
- Avg fetch_page calls: 1.8
- Avg input tokens: 304205
- Avg output tokens: 3631
- Avg thinking tokens: 2410

## Accuracy by Level

| Level | Correct | Total | Accuracy |
|-------|---------|-------|----------|
| L1 | 3 | 6 | 50% |
| L2 | 3 | 6 | 50% |
| L3 | 1 | 6 | 17% |

## vs 007 Claude Haiku 4.5 (text_only baseline)

| Metric | MiroThinker-1.7-mini | Claude Haiku 4.5 (007) |
|--------|---------------------|------------------------|
| Accuracy | 38.9% | (see 007 report) |
| Avg latency | 225.1s | (see 007 report) |
| Avg input tokens | 304205 | (see 007 report) |

## Per-Task Results

| Run | Task ID | L | OK | Answer | Turns | S | F | Lat | Think tok |
|-----|---------|---|----|----|-------|---|---|-----|-----------|
| 1 | dc28cf18-6431- | L1 | N |                           | 1 | 0 | 0 | 398s | 8361 |
| 1 | 5d0080cb-90d7- | L1 | Y | 0.1777                    | 12 | 5 | 6 | 117s | 818 |
| 1 | b816bfce-3d80- | L1 | Y | fluffy                    | 29 | 28 | 0 | 212s | 1708 |
| 1 | 853c8244-429e- | L2 | Y | 11                        | 9 | 3 | 2 | 79s | 633 |
| 1 | e0c10771-d627- | L2 | N |                           | 30 | 30 | 0 | 286s | 2657 |
| 1 | b4cc024b-3f5e- | L2 | Y | Russian-German Legion     | 12 | 4 | 6 | 128s | 851 |
| 1 | e961a717-6b25- | L3 | N | 11                        | 8 | 2 | 2 | 160s | 2282 |
| 1 | 72c06643-a2fa- | L3 | N |                           | 30 | 30 | 0 | 262s | 2485 |
| 1 | 676e5e31-a554- | L3 | N |                           | 30 | 26 | 4 | 282s | 1494 |
| 2 | dc28cf18-6431- | L1 | N |                           | 30 | 30 | 0 | 743s | 11902 |
| 2 | 5d0080cb-90d7- | L1 | N | jina_tool_name>
fetch_pag... | 3 | 1 | 1 | 25s | 154 |
| 2 | b816bfce-3d80- | L1 | Y | fluffy                    | 29 | 28 | 0 | 223s | 1593 |
| 2 | 853c8244-429e- | L2 | N |                           | 30 | 21 | 9 | 284s | 1660 |
| 2 | e0c10771-d627- | L2 | Y | 234.9                     | 12 | 11 | 0 | 103s | 858 |
| 2 | b4cc024b-3f5e- | L2 | N |                           | 30 | 5 | 3 | 245s | 2254 |
| 2 | e961a717-6b25- | L3 | Y | 12                        | 28 | 27 | 0 | 231s | 2223 |
| 2 | 72c06643-a2fa- | L3 | N |                           | 9 | 0 | 0 | 48s | 435 |
| 2 | 676e5e31-a554- | L3 | N |                           | 30 | 30 | 0 | 223s | 1019 |