# Experiment 001: Mask vs Remove — Results

Generated: 2026-03-22 13:00:15

## Summary

| Strategy | Runs | Accuracy | Avg Latency (s) | Avg Input Tokens | Avg Output Tokens | Invalid Calls |
|----------|------|----------|-----------------|------------------|-------------------|---------------|
| all      |    3 |   95.0% |            8.15 |             2262 |               304 |           0.0 |
| remove   |    3 |   98.3% |            6.38 |              793 |               228 |           0.0 |
| mask     |    3 |   91.7% |            7.95 |             2423 |               295 |           0.0 |

## Per-Task Results (Last Run)

| Task ID | Domain | Strategy | Correct | Tool Called | Latency (s) | Tokens |
|---------|--------|----------|---------|------------|-------------|--------|
| calc_01  |        | all      | Y       | calculator |       12.08 |   5724 |
| calc_02  |        | all      | Y       | calculator |       10.34 |   2842 |
| calc_03  |        | all      | Y       | calculator |        6.78 |   2508 |
| rev_01   |        | all      | Y       | string_reverse |        8.69 |   2548 |
| rev_02   |        | all      | Y       | string_reverse |        7.91 |   2498 |
| char_01  |        | all      | Y       | char_count |        4.91 |   2351 |
| char_02  |        | all      | Y       |            |       11.88 |   1516 |
| char_03  |        | all      | N       | char_count |        4.71 |   2331 |
| base_01  |        | all      | Y       | base_convert |        5.11 |   2372 |
| base_02  |        | all      | Y       | base_convert |        5.53 |   2416 |
| base_03  |        | all      | Y       | base_convert |        5.86 |   2416 |
| cipher_01 |        | all      | Y       | caesar_cipher |        7.28 |   2488 |
| cipher_02 |        | all      | Y       |            |       11.98 |   1513 |
| temp_01  |        | all      | Y       | temperature_convert |        4.79 |   2308 |
| temp_02  |        | all      | Y       | temperature_convert |        4.33 |   2291 |
| temp_03  |        | all      | Y       | temperature_convert |       10.45 |   2673 |
| gcd_01   |        | all      | Y       | gcd        |       14.11 |   2985 |
| gcd_02   |        | all      | Y       | gcd        |       11.49 |   2933 |
| wc_01    |        | all      | Y       | word_count |       10.11 |   2699 |
| wc_02    |        | all      | Y       | word_count |        6.40 |   2480 |
| calc_01  |        | remove   | Y       | calculator |        9.07 |   1279 |
| calc_02  |        | remove   | Y       | calculator |        7.62 |   1158 |
| calc_03  |        | remove   | Y       | calculator |        6.07 |    978 |
| rev_01   |        | remove   | Y       | string_reverse |        4.93 |    820 |
| rev_02   |        | remove   | Y       | string_reverse |        4.88 |    817 |
| char_01  |        | remove   | Y       | char_count |        8.32 |   1217 |
| char_02  |        | remove   | Y       | char_count |        6.68 |   1065 |
| char_03  |        | remove   | Y       |            |       11.88 |    787 |
| base_01  |        | remove   | Y       | base_convert |        5.32 |   1010 |
| base_02  |        | remove   | Y       | base_convert |        4.90 |    978 |
| base_03  |        | remove   | Y       | base_convert |        5.09 |    980 |
| cipher_01 |        | remove   | Y       | caesar_cipher |        5.67 |   1048 |
| cipher_02 |        | remove   | Y       | caesar_cipher |        9.25 |   1374 |
| temp_01  |        | remove   | Y       | temperature_convert |        4.89 |    940 |
| temp_02  |        | remove   | Y       | temperature_convert |        5.37 |   1011 |
| temp_03  |        | remove   | Y       | temperature_convert |        6.36 |   1084 |
| gcd_01   |        | remove   | Y       | gcd        |        4.27 |    812 |
| gcd_02   |        | remove   | Y       | gcd        |        4.26 |    823 |
| wc_01    |        | remove   | Y       | word_count |        6.99 |   1057 |
| wc_02    |        | remove   | Y       | word_count |        6.75 |   1022 |
| calc_01  |        | mask     | Y       | calculator |       16.66 |   5086 |
| calc_02  |        | mask     | Y       | calculator |        7.25 |   2690 |
| calc_03  |        | mask     | Y       | calculator |        6.01 |   2566 |
| rev_01   |        | mask     | Y       | string_reverse |        8.72 |   2705 |
| rev_02   |        | mask     | Y       | string_reverse |        9.28 |   2728 |
| char_01  |        | mask     | Y       | char_count |        4.88 |   2477 |
| char_02  |        | mask     | N       |            |       11.95 |   1579 |
| char_03  |        | mask     | N       | char_count |        4.67 |   2437 |
| base_01  |        | mask     | Y       | base_convert |        4.70 |   2452 |
| base_02  |        | mask     | Y       | base_convert |        5.54 |   2542 |
| base_03  |        | mask     | Y       | base_convert |        5.86 |   2546 |
| cipher_01 |        | mask     | Y       | caesar_cipher |        4.94 |   2474 |
| cipher_02 |        | mask     | Y       | caesar_cipher |       14.44 |   4896 |
| temp_01  |        | mask     | Y       | temperature_convert |        4.73 |   2434 |
| temp_02  |        | mask     | Y       | temperature_convert |        4.52 |   2417 |
| temp_03  |        | mask     | Y       | temperature_convert |        6.20 |   2485 |
| gcd_01   |        | mask     | Y       | gcd        |       12.58 |   3004 |
| gcd_02   |        | mask     | Y       | gcd        |        9.38 |   2883 |
| wc_01    |        | mask     | Y       | word_count |        8.82 |   2833 |
| wc_02    |        | mask     | Y       | word_count |       10.05 |   2824 |

## Latency Analysis

### all
- Mean: 8.149s
- Median: 7.278s
- P90: 11.984s
- Min: 4.268s
- Max: 14.783s
- First 5 avg: 4.479s
- Last 5 avg: 13.746s

### remove
- Mean: 6.380s
- Median: 5.905s
- P90: 9.245s
- Min: 4.223s
- Max: 11.883s
- First 5 avg: 4.247s
- Last 5 avg: 10.596s

### mask
- Mean: 7.949s
- Median: 7.149s
- P90: 12.713s
- Min: 4.299s
- Max: 17.229s
- First 5 avg: 4.481s
- Last 5 avg: 15.185s
