# Experiment 004: KV Cache Stability — Results

Generated: 2026-03-22 18:35:59

50 tools (all shown), 20 tasks, sequential execution, temperature=0.0

## Summary

| Strategy    | Runs | Accuracy | Avg Latency | Avg TTFT | Cache Hit Rate | Avg Input Tok |
|-------------|------|----------|-------------|----------|----------------|---------------|
| stable      |    1 |   80.0% |       12.07s |   0.922s |         99.5% |         11948 |
| timestamp_s |    1 |   80.0% |       12.44s |   1.230s |          0.3% |         10266 |
| truncate    |    1 |   75.0% |       13.28s |   0.936s |         99.0% |         13036 |

## TTFT by Turn Number (Primary Result)

Mean TTFT at each turn index, aggregated across all tasks.

H1: stable TTFT should *decrease* after turn 1 (cross-task cache warming).
H2: timestamp_s TTFT should stay *flat/high* (cache miss every turn).
H3: truncate TTFT should *spike* at turns where truncation kicks in (turn 3+).

| Turn # | stable             | timestamp_s        | truncate           |
|--------|--------------------|--------------------|--------------------|
|      1 | 0.914s (n=20)      | 1.183s (n=20)      | 0.901s (n=20)      |
|      2 | 0.897s (n=19)      | 1.281s (n=19)      | 0.903s (n=19)      |
|      3 | 1.027s (n= 3)      | 1.199s (n= 1)      | 1.054s (n= 3)      |
|      4 | 1.028s (n= 3)      | 1.213s (n= 1)      | 1.049s (n= 3)      |
|      5 | 0.931s (n= 3)      | 1.230s (n= 1)      | 0.977s (n= 3)      |
|      6 | 0.877s (n= 1)      |                    | 0.984s (n= 2)      |
|      7 |                    |                    | 1.022s (n= 1)      |
|      8 |                    |                    | 1.037s (n= 1)      |
|      9 |                    |                    | 1.050s (n= 1)      |
|     10 |                    |                    | 1.046s (n= 1)      |

## TTFT by Task Index (stable strategy, run 1)

Shows whether turn-1 TTFT decreases as more tasks are processed (evidence of cross-task prefix cache warmup).

| Task | Turn 1 | Turn 2 | Turn 3 | Turn 4 | Turn 5 | Turn 6 | Turn 7 | Turn 8 | Turn 9 | Turn 10 |
|------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
|    0 | 1.534s | 0.866s |         |         |         |         |         |         |         |         |
|    1 | 0.879s | 0.883s |         |         |         |         |         |         |         |         |
|    2 | 0.910s | 0.868s |         |         |         |         |         |         |         |         |
|    3 | 0.889s | 1.015s | 1.028s | 1.019s | 0.870s |         |         |         |         |         |
|    4 | 0.872s | 0.868s |         |         |         |         |         |         |         |         |
|    5 | 0.869s | 1.029s | 1.022s | 1.038s | 0.886s |         |         |         |         |         |
|    6 | 0.911s | 0.888s |         |         |         |         |         |         |         |         |
|    7 | 0.884s | 0.865s |         |         |         |         |         |         |         |         |
|    8 | 0.880s |         |         |         |         |         |         |         |         |         |
|    9 | 0.869s | 0.878s |         |         |         |         |         |         |         |         |
|   10 | 0.873s | 0.892s |         |         |         |         |         |         |         |         |
|   11 | 0.868s | 0.863s |         |         |         |         |         |         |         |         |
|   12 | 0.909s | 0.859s |         |         |         |         |         |         |         |         |
|   13 | 0.869s | 0.872s |         |         |         |         |         |         |         |         |
|   14 | 0.867s | 1.033s | 1.031s | 1.028s | 1.038s | 0.877s |         |         |         |         |
|   15 | 0.892s | 0.880s |         |         |         |         |         |         |         |         |
|   16 | 0.891s | 0.871s |         |         |         |         |         |         |         |         |
|   17 | 0.871s | 0.869s |         |         |         |         |         |         |         |         |
|   18 | 0.864s | 0.868s |         |         |         |         |         |         |         |         |
|   19 | 0.875s | 0.883s |         |         |         |         |         |         |         |         |

## Turn-1 TTFT by Task Index (all strategies)

Turn 1 is the first LLM call per task (system prompt + task prompt only).
For stable, this TTFT should decrease as the system prompt prefix warms up.
For timestamp_s, this TTFT should stay high (new timestamp each call).

| Task | stable      | timestamp_s | truncate    |
|------|-------------|-------------|-------------|
|    0 | 1.534s      | 1.156s      | 1.227s      |
|    1 | 0.879s      | 1.146s      | 0.878s      |
|    2 | 0.910s      | 1.180s      | 0.880s      |
|    3 | 0.889s      | 1.243s      | 0.908s      |
|    4 | 0.872s      | 1.163s      | 0.867s      |
|    5 | 0.869s      | 1.173s      | 0.882s      |
|    6 | 0.911s      | 1.175s      | 0.879s      |
|    7 | 0.884s      | 1.164s      | 0.869s      |
|    8 | 0.880s      | 1.171s      | 0.871s      |
|    9 | 0.869s      | 1.200s      | 0.891s      |
|   10 | 0.873s      | 1.148s      | 0.887s      |
|   11 | 0.868s      | 1.187s      | 0.890s      |
|   12 | 0.909s      | 1.422s      | 0.941s      |
|   13 | 0.869s      | 1.149s      | 0.883s      |
|   14 | 0.867s      | 1.143s      | 0.876s      |
|   15 | 0.892s      | 1.157s      | 0.892s      |
|   16 | 0.891s      | 1.179s      | 0.880s      |
|   17 | 0.871s      | 1.185s      | 0.881s      |
|   18 | 0.864s      | 1.155s      | 0.874s      |
|   19 | 0.875s      | 1.160s      | 0.867s      |

## Prefix Cache Metrics

| Strategy    | Run | Queries (delta) | Hits (delta) | Hit Rate |
|-------------|-----|-----------------|--------------|----------|
| stable      |   1 |         238,953 |      237,760 |   99.5% |
| timestamp_s |   1 |         205,326 |          656 |    0.3% |
| truncate    |   1 |         260,720 |      258,208 |   99.0% |

## Per-Task Results (Run 1)

| Task ID | Strategy    | Correct | Steps | Latency | Avg TTFT | Tokens |
|---------|-------------|---------|-------|---------|----------|--------|
| chain4_calc_bin_char_power          | stable      | N       |  4/4 |    8.70s |   1.200s |   9871 |
| chain4_reverse_len_mod_even         | stable      | Y       |  4/4 |   11.56s |   0.881s |  10160 |
| chain4_wc_power_base_upper          | stable      | Y       |  4/4 |    9.30s |   0.889s |  10000 |
| chain4_caesar_reverse_len_calc      | stable      | Y       |  4/4 |   11.30s |   0.964s |  24621 |
| chain5_calc_gcd_bin_char_power      | stable      | Y       |  5/5 |   13.46s |   0.870s |  10414 |
| chain4_temp_round_mod_abs           | stable      | Y       |  4/10 |   13.29s |   0.969s |  25066 |
| chain5_reverse_upper_len_lcm_bin    | stable      | Y       |  5/5 |    9.38s |   0.899s |  10022 |
| chain4_calc_floor_gcd_even          | stable      | Y       |  4/4 |   12.88s |   0.875s |  10308 |
| chain4_lower_replace_char_calc      | stable      | N       |  0/4 |   24.14s |   0.880s |   5654 |
| chain5_calc_mod_power_sumdig_even   | stable      | N       |  5/5 |    9.86s |   0.873s |  10046 |
| chain4_sort_first3_upper_len        | stable      | Y       |  4/4 |   16.25s |   0.882s |  10558 |
| chain5_wc_gcd_power_bin_char        | stable      | Y       |  5/5 |   10.74s |   0.866s |  10150 |
| chain4_unique_len_max_round         | stable      | Y       |  4/4 |   13.90s |   0.884s |  10379 |
| chain4_calc_base_lower_len          | stable      | Y       |  4/4 |    9.45s |   0.871s |   9983 |
| chain5_temp_calc_mod_power_sumdig   | stable      | Y       |  5/5 |   12.15s |   0.979s |  29596 |
| chain4_repeat_len_floor_bin         | stable      | Y       |  4/4 |   11.24s |   0.886s |  10137 |
| chain5_caesar_char_lcm_mod_even     | stable      | Y       |  5/5 |   10.82s |   0.881s |  10149 |
| chain4_slice_reverse_upper_len      | stable      | N       |  4/4 |   12.43s |   0.870s |  10237 |
| chain5_calc_pct_round_floor_bin     | stable      | Y       |  5/5 |   10.48s |   0.866s |  10125 |
| chain6_reverse_len_power_bin_char_calc | stable      | Y       |  6/6 |   10.09s |   0.879s |  10143 |
| chain4_calc_bin_char_power          | timestamp_s | N       |  4/4 |    8.97s |   1.173s |   9921 |
| chain4_reverse_len_mod_even         | timestamp_s | Y       |  4/4 |    9.61s |   1.171s |   9958 |
| chain4_wc_power_base_upper          | timestamp_s | Y       |  4/4 |   11.37s |   1.187s |  10136 |
| chain4_caesar_reverse_len_calc      | timestamp_s | Y       |  4/4 |    9.62s |   1.221s |   9984 |
| chain5_calc_gcd_bin_char_power      | timestamp_s | Y       |  5/5 |   12.03s |   1.183s |  10266 |
| chain4_temp_round_mod_abs           | timestamp_s | Y       |  4/10 |   14.36s |   1.219s |  25041 |
| chain5_reverse_upper_len_lcm_bin    | timestamp_s | Y       |  5/5 |    9.51s |   1.211s |  10002 |
| chain4_calc_floor_gcd_even          | timestamp_s | Y       |  4/4 |   11.34s |   1.178s |  10154 |
| chain4_lower_replace_char_calc      | timestamp_s | N       |  0/4 |   24.53s |   1.171s |   5679 |
| chain5_calc_mod_power_sumdig_even   | timestamp_s | N       |  5/5 |   10.44s |   1.193s |  10096 |
| chain4_sort_first3_upper_len        | timestamp_s | Y       |  4/4 |   13.73s |   1.169s |  10330 |
| chain5_wc_gcd_power_bin_char        | timestamp_s | Y       |  5/5 |   14.47s |   1.973s |  10318 |
| chain4_unique_len_max_round         | timestamp_s | Y       |  4/4 |    9.34s |   1.292s |   9941 |
| chain4_calc_base_lower_len          | timestamp_s | Y       |  4/4 |   14.23s |   1.170s |  10385 |
| chain5_temp_calc_mod_power_sumdig   | timestamp_s | Y       |  5/5 |   14.92s |   1.171s |  10478 |
| chain4_repeat_len_floor_bin         | timestamp_s | Y       |  4/4 |   12.17s |   1.166s |  10193 |
| chain5_caesar_char_lcm_mod_even     | timestamp_s | Y       |  5/5 |   11.39s |   1.188s |  10169 |
| chain4_slice_reverse_upper_len      | timestamp_s | N       |  4/4 |   13.24s |   1.184s |  10287 |
| chain5_calc_pct_round_floor_bin     | timestamp_s | Y       |  5/5 |   12.70s |   1.176s |  10299 |
| chain6_reverse_len_power_bin_char_calc | timestamp_s | Y       |  6/6 |   10.87s |   1.182s |  10193 |
| chain4_calc_bin_char_power          | truncate    | N       |  4/4 |    8.49s |   1.047s |   9871 |
| chain4_reverse_len_mod_even         | truncate    | Y       |  4/4 |   11.58s |   0.881s |  10144 |
| chain4_wc_power_base_upper          | truncate    | Y       |  4/4 |    9.21s |   0.901s |   9976 |
| chain4_caesar_reverse_len_calc      | truncate    | Y       |  4/4 |   16.09s |   0.977s |  24302 |
| chain5_calc_gcd_bin_char_power      | truncate    | Y       |  5/5 |   13.96s |   0.868s |  10450 |
| chain4_temp_round_mod_abs           | truncate    | N       | 10/10 |   21.65s |   1.039s |  48193 |
| chain5_reverse_upper_len_lcm_bin    | truncate    | Y       |  5/5 |    9.52s |   0.881s |  10022 |
| chain4_calc_floor_gcd_even          | truncate    | Y       |  4/4 |   14.73s |   0.869s |  10474 |
| chain4_lower_replace_char_calc      | truncate    | N       |  0/4 |   24.05s |   0.871s |   5654 |
| chain5_calc_mod_power_sumdig_even   | truncate    | N       |  5/5 |    9.66s |   0.889s |  10046 |
| chain4_sort_first3_upper_len        | truncate    | Y       |  4/4 |   13.05s |   0.887s |  10280 |
| chain5_wc_gcd_power_bin_char        | truncate    | Y       |  5/5 |   11.39s |   0.878s |  10218 |
| chain4_unique_len_max_round         | truncate    | Y       |  4/4 |   13.73s |   0.905s |  10367 |
| chain4_calc_base_lower_len          | truncate    | Y       |  4/4 |   10.79s |   0.880s |  10121 |
| chain5_temp_calc_mod_power_sumdig   | truncate    | Y       |  5/5 |   21.72s |   0.974s |  29267 |
| chain4_repeat_len_floor_bin         | truncate    | Y       |  4/4 |   11.27s |   0.882s |  10143 |
| chain5_caesar_char_lcm_mod_even     | truncate    | Y       |  5/5 |   11.37s |   0.882s |  10187 |
| chain4_slice_reverse_upper_len      | truncate    | N       |  4/4 |   12.40s |   0.875s |  10237 |
| chain5_calc_pct_round_floor_bin     | truncate    | Y       |  5/5 |   10.88s |   0.881s |  10157 |
| chain6_reverse_len_power_bin_char_calc | truncate    | Y       |  6/6 |   10.04s |   0.874s |  10143 |