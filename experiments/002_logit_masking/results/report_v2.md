# Experiment 002 (v2): Static Mask vs Remove — Results

Generated: 2026-03-22 16:22:27

Strategy design: per-task static (tool list constant across turns)

## Summary

| Strategy | Runs | Accuracy | Step Completion | Avg Latency (s) | Avg Input Tok | Avg Output Tok | Invalid Calls |
|----------|------|----------|-----------------|-----------------|---------------|----------------|---------------|
| all        |    3 |  100.0% |         100.0% |           10.19 |          2554 |            383 |           0.0 |
| remove     |    3 |   93.3% |         100.0% |            9.97 |          1310 |            380 |           0.0 |
| logit_mask |    3 |  100.0% |         100.0% |           10.46 |          2591 |            399 |           0.0 |
| desc_mask  |    3 |   96.7% |         100.0% |           10.40 |          2688 |            390 |           0.0 |

## Per-Task Results (Last Run)

| Task ID | Strategy | Correct | Tools Called | Steps | Latency (s) | Tokens |
|---------|----------|---------|-------------|-------|-------------|--------|
| chain_calc_gcd             | all        | Y       | calculator,gcd                 |  2/2 |        6.40 |   2563 |
| chain_temp_base            | all        | Y       | temperature_convert,base_convert |  2/2 |        7.33 |   2689 |
| chain_reverse_char         | all        | Y       | string_reverse,char_count      |  2/2 |        7.02 |   2623 |
| chain_calc_base            | all        | Y       | calculator,base_convert        |  2/2 |       11.30 |   3013 |
| chain_cipher_reverse       | all        | Y       | caesar_cipher,string_reverse   |  2/2 |       16.82 |   3479 |
| chain_wc_calc              | all        | Y       | word_count,calculator          |  2/2 |        9.81 |   2863 |
| chain_calc_temp            | all        | Y       | calculator,temperature_convert |  2/2 |        9.46 |   2852 |
| chain_reverse_wc           | all        | Y       | string_reverse,word_count      |  2/2 |        6.26 |   2559 |
| chain_gcd_base             | all        | Y       | gcd,base_convert               |  2/2 |       16.49 |   3477 |
| chain_cipher_char          | all        | Y       | caesar_cipher,char_count       |  2/2 |       11.10 |   2934 |
| chain_base_calc            | all        | Y       | base_convert,calculator        |  2/2 |        6.47 |   2590 |
| chain_temp_calc            | all        | Y       | temperature_convert,calculator |  2/2 |        9.53 |   2851 |
| chain_calc_cipher          | all        | Y       | calculator,caesar_cipher       |  2/2 |        9.13 |   2829 |
| chain_wc_gcd               | all        | Y       | word_count,gcd                 |  2/2 |       10.77 |   2955 |
| chain_char_calc            | all        | Y       | char_count,calculator          |  2/2 |       15.93 |   3413 |
| chain_reverse_cipher       | all        | Y       | string_reverse,caesar_cipher   |  2/2 |        6.91 |   2625 |
| chain_calc_gcd2            | all        | Y       | calculator,gcd                 |  2/2 |       11.81 |   3044 |
| chain_temp_gcd             | all        | Y       | temperature_convert,gcd        |  2/2 |        9.84 |   2898 |
| chain_3step_calc_base_char | all        | Y       | calculator,base_convert,char_count |  3/3 |        8.54 |   2874 |
| chain_3step_reverse_char_calc | all        | Y       | string_reverse,char_count,calculator |  3/3 |        7.35 |   2723 |
| chain_calc_gcd             | remove     | Y       | calculator,gcd                 |  2/2 |       14.29 |   1995 |
| chain_temp_base            | remove     | Y       | temperature_convert,base_convert |  2/2 |        6.59 |   1507 |
| chain_reverse_char         | remove     | Y       | string_reverse,char_count      |  2/2 |        6.16 |   1253 |
| chain_calc_base            | remove     | Y       | calculator,base_convert        |  2/2 |        8.03 |   1551 |
| chain_cipher_reverse       | remove     | N       | caesar_cipher,string_reverse   |  2/2 |       10.35 |   1687 |
| chain_wc_calc              | remove     | Y       | word_count,calculator          |  2/2 |       13.62 |   1911 |
| chain_calc_temp            | remove     | Y       | calculator,temperature_convert |  2/2 |        9.98 |   1716 |
| chain_reverse_wc           | remove     | Y       | string_reverse,word_count      |  2/2 |       11.27 |   1651 |
| chain_gcd_base             | remove     | Y       | gcd,base_convert               |  2/2 |       15.21 |   2161 |
| chain_cipher_char          | remove     | Y       | caesar_cipher,char_count       |  2/2 |        8.99 |   1642 |
| chain_base_calc            | remove     | Y       | base_convert,calculator        |  2/2 |        8.56 |   1606 |
| chain_temp_calc            | remove     | N       | temperature_convert,calculator |  2/2 |        6.79 |   1433 |
| chain_calc_cipher          | remove     | Y       | calculator,caesar_cipher       |  2/2 |        8.91 |   1643 |
| chain_wc_gcd               | remove     | Y       | word_count,gcd                 |  2/2 |        8.01 |   1421 |
| chain_char_calc            | remove     | Y       | char_count,calculator          |  2/2 |       10.96 |   1723 |
| chain_reverse_cipher       | remove     | Y       | string_reverse,caesar_cipher   |  2/2 |       12.11 |   1831 |
| chain_calc_gcd2            | remove     | Y       | calculator,gcd                 |  2/2 |       16.42 |   2180 |
| chain_temp_gcd             | remove     | Y       | temperature_convert,gcd        |  2/2 |        8.95 |   1612 |
| chain_3step_calc_base_char | remove     | Y       | calculator,base_convert,char_count |  3/3 |        7.68 |   1796 |
| chain_3step_reverse_char_calc | remove     | Y       | string_reverse,char_count,calculator |  3/3 |        7.55 |   1611 |
| chain_calc_gcd             | logit_mask | Y       | calculator,gcd                 |  2/2 |       13.17 |   3167 |
| chain_temp_base            | logit_mask | Y       | temperature_convert,base_convert |  2/2 |        9.68 |   2897 |
| chain_reverse_char         | logit_mask | Y       | string_reverse,char_count      |  2/2 |        6.96 |   2623 |
| chain_calc_base            | logit_mask | Y       | calculator,base_convert        |  2/2 |        9.47 |   2855 |
| chain_cipher_reverse       | logit_mask | Y       | caesar_cipher,string_reverse   |  2/2 |       16.79 |   3477 |
| chain_wc_calc              | logit_mask | Y       | word_count,calculator          |  2/2 |        7.49 |   2673 |
| chain_calc_temp            | logit_mask | Y       | calculator,temperature_convert |  2/2 |       12.77 |   3138 |
| chain_reverse_wc           | logit_mask | Y       | string_reverse,word_count      |  2/2 |        6.21 |   2559 |
| chain_gcd_base             | logit_mask | Y       | gcd,base_convert               |  2/2 |       17.06 |   3529 |
| chain_cipher_char          | logit_mask | Y       | caesar_cipher,char_count       |  2/2 |       10.61 |   2962 |
| chain_base_calc            | logit_mask | Y       | base_convert,calculator        |  2/2 |        6.23 |   2590 |
| chain_temp_calc            | logit_mask | Y       | temperature_convert,calculator,calculator |  3/2 |       13.99 |   4784 |
| chain_calc_cipher          | logit_mask | Y       | calculator,caesar_cipher       |  2/2 |        8.81 |   2811 |
| chain_wc_gcd               | logit_mask | Y       | word_count,gcd                 |  2/2 |        9.76 |   2883 |
| chain_char_calc            | logit_mask | Y       | char_count,calculator          |  2/2 |       16.07 |   3419 |
| chain_reverse_cipher       | logit_mask | Y       | string_reverse,caesar_cipher   |  2/2 |        6.92 |   2625 |
| chain_calc_gcd2            | logit_mask | Y       | calculator,gcd                 |  2/2 |       10.59 |   2956 |
| chain_temp_gcd             | logit_mask | Y       | temperature_convert,gcd        |  2/2 |        9.97 |   2898 |
| chain_3step_calc_base_char | logit_mask | Y       | calculator,base_convert,char_count |  3/3 |        8.92 |   2892 |
| chain_3step_reverse_char_calc | logit_mask | Y       | string_reverse,char_count,calculator |  3/3 |        7.50 |   2723 |
| chain_calc_gcd             | desc_mask  | Y       | calculator,gcd                 |  2/2 |        9.96 |   2995 |
| chain_temp_base            | desc_mask  | Y       | temperature_convert,base_convert |  2/2 |        8.22 |   2861 |
| chain_reverse_char         | desc_mask  | Y       | string_reverse,char_count      |  2/2 |        6.97 |   2731 |
| chain_calc_base            | desc_mask  | Y       | calculator,base_convert        |  2/2 |       12.21 |   3191 |
| chain_cipher_reverse       | desc_mask  | Y       | caesar_cipher,string_reverse,caesar_cipher,string_reverse |  4/2 |       26.77 |   5002 |
| chain_wc_calc              | desc_mask  | Y       | word_count,calculator          |  2/2 |        8.74 |   2871 |
| chain_calc_temp            | desc_mask  | Y       | calculator,temperature_convert |  2/2 |       10.48 |   3034 |
| chain_reverse_wc           | desc_mask  | Y       | string_reverse,word_count      |  2/2 |        5.85 |   2635 |
| chain_gcd_base             | desc_mask  | Y       | gcd,base_convert               |  2/2 |       18.63 |   3745 |
| chain_cipher_char          | desc_mask  | Y       | caesar_cipher,char_count       |  2/2 |       10.78 |   3066 |
| chain_base_calc            | desc_mask  | Y       | base_convert,calculator        |  2/2 |        7.54 |   2794 |
| chain_temp_calc            | desc_mask  | N       | temperature_convert,calculator |  2/2 |        7.76 |   2803 |
| chain_calc_cipher          | desc_mask  | Y       | calculator,caesar_cipher       |  2/2 |        8.80 |   2901 |
| chain_wc_gcd               | desc_mask  | Y       | word_count,gcd                 |  2/2 |        9.50 |   2957 |
| chain_char_calc            | desc_mask  | Y       | char_count,calculator          |  2/2 |       17.91 |   3671 |
| chain_reverse_cipher       | desc_mask  | Y       | string_reverse,caesar_cipher   |  2/2 |        8.11 |   2823 |
| chain_calc_gcd2            | desc_mask  | Y       | calculator,gcd                 |  2/2 |       11.57 |   3126 |
| chain_temp_gcd             | desc_mask  | Y       | temperature_convert,gcd        |  2/2 |        9.45 |   2952 |
| chain_3step_calc_base_char | desc_mask  | Y       | calculator,base_convert,char_count |  3/3 |        9.23 |   2974 |
| chain_3step_reverse_char_calc | desc_mask  | Y       | string_reverse,char_count,calculator |  3/3 |        7.66 |   2813 |

## Latency Analysis

### all
- Mean: 10.187s
- Median: 9.526s
- P90: 16.485s
- Min: 6.094s, Max: 24.660s

### remove
- Mean: 9.972s
- Median: 9.096s
- P90: 15.213s
- Min: 6.155s, Max: 16.819s

### logit_mask
- Mean: 10.461s
- Median: 9.677s
- P90: 16.362s
- Min: 6.211s, Max: 27.456s

### desc_mask
- Mean: 10.398s
- Median: 9.454s
- P90: 16.271s
- Min: 5.840s, Max: 26.810s

## Token Map (Logit Mask)

| Tool Name | Token IDs Blocked |
|-----------|-------------------|
| base_convert | [2331, 3152] |
| caesar_cipher | [924, 2162] |
| calculator | [29952, 88821] |
| char_count | [1161, 1762] |
| gcd | [44858, 91289] |
| string_reverse | [914, 917] |
| temperature_convert | [9315, 34558] |
| word_count | [1158, 3409] |
