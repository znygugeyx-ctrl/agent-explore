# Experiment 010: Qwen3-30B-A3B-Thinking-2507 (base) — Results

Generated: 2026-03-29 00:09:54

## Summary

- Runs: 2, Tasks: 9
- **Accuracy: 33.3%** (6/18)
- Avg latency: 188.8s | Avg turns: 2.3
- Avg web_search: 0.8 | Avg fetch_page: 0.5
- Avg input tokens: 5376 | Avg output tokens: 3637

## Accuracy by Level

| Level | Correct | Total | % |
|-------|---------|-------|---|
| L1 | 3 | 6 | 50% |
| L2 | 2 | 6 | 33% |
| L3 | 1 | 6 | 17% |

## vs Baselines

| Model | Size | Accuracy | Latency | Input tok | Tool format |
|-------|------|----------|---------|-----------|-------------|
| **Qwen3-30B-A3B-Thinking (this)** | 30B (3B active) | **33.3%** | 189s | 5376 | JSON hermes |
| MiroThinker-1.7-mini (008, 256K) | 30B | 38.9% | 225s | 304205 | XML/MCP |
| Claude Haiku 4.5 (007) | ~3.5B | 67.3% | 76s | 179034 | JSON Bedrock |

## Per-Task Results

| Run | Task | L | OK | Answer | Turns | S | F | Lat |
|-----|------|---|----|----|-------|---|---|-----|
| 1 | dc28cf18-6431- | L1 | Y | Okay, let's see. I need t... | 1 | 0 | 0 | 247s |
| 1 | 5d0080cb-90d7- | L1 | Y | Okay, let me look through... | 5 | 2 | 2 | 135s |
| 1 | b816bfce-3d80- | L1 | N | Okay, let's see. The user... | 3 | 1 | 1 | 125s |
| 1 | 853c8244-429e- | L2 | N | Okay, the user is asking ... | 1 | 0 | 0 | 116s |
| 1 | e0c10771-d627- | L2 | Y | Okay, let's see. The user... | 2 | 1 | 0 | 49s |
| 1 | b4cc024b-3f5e- | L2 | N | Okay, let's see. The user... | 2 | 1 | 0 | 263s |
| 1 | e961a717-6b25- | L3 | N | Okay, let's tackle this s... | 2 | 1 | 0 | 284s |
| 1 | 72c06643-a2fa- | L3 | N | Okay, the user is asking ... | 3 | 1 | 1 | 285s |
| 1 | 676e5e31-a554- | L3 | N | Okay, let's tackle this q... | 1 | 0 | 0 | 163s |
| 2 | dc28cf18-6431- | L1 | N | Okay, let's tackle this p... | 1 | 0 | 0 | 321s |
| 2 | 5d0080cb-90d7- | L1 | Y | Okay, let's see. The user... | 2 | 1 | 0 | 45s |
| 2 | b816bfce-3d80- | L1 | N | Okay, let's see. The user... | 3 | 1 | 1 | 127s |
| 2 | 853c8244-429e- | L2 | N | Okay, let's see. The user... | 1 | 0 | 0 | 183s |
| 2 | e0c10771-d627- | L2 | Y | Okay, let's see. The user... | 2 | 1 | 0 | 105s |
| 2 | b4cc024b-3f5e- | L2 | N | Okay, let's break this do... | 3 | 1 | 1 | 280s |
| 2 | e961a717-6b25- | L3 | Y | Okay, let's tackle this q... | 3 | 1 | 1 | 204s |
| 2 | 72c06643-a2fa- | L3 | N | Okay, let's see. The user... | 2 | 1 | 0 | 234s |
| 2 | 676e5e31-a554- | L3 | N | Okay, let's try to figure... | 4 | 1 | 2 | 231s |