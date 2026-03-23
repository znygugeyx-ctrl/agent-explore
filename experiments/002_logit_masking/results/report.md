# Experiment 002: Logit Masking + Multi-Turn — Results

Generated: 2026-03-22 15:06:58

## Summary

| Strategy | Runs | Accuracy | Step Completion | Avg Latency (s) | Avg Input Tok | Avg Output Tok | Invalid Calls |
|----------|------|----------|-----------------|-----------------|---------------|----------------|---------------|
| all        |    3 |   96.7% |         100.0% |            9.49 |          2534 |            364 |          22.0 |
| remove     |    3 |   83.3% |          61.7% |           16.79 |          1819 |            702 |          11.3 |
| logit_mask |    3 |   95.0% |         100.0% |           12.90 |          4526 |            479 |          12.0 |
| desc_mask  |    3 |  100.0% |         100.0% |            9.96 |          2687 |            383 |          22.0 |

## Per-Task Results (Last Run)

| Task ID | Steps | Strategy | Correct | Tools Called | Steps Done | Latency (s) | Tokens |
|---------|-------|----------|---------|-------------|------------|-------------|--------|
| chain_calc_gcd             |     2 | all        | Y       | calculator,gcd (!)   |          2 |        6.08 |   2563 |
| chain_temp_base            |     2 | all        | Y       | temperature_convert,base_convert (!) |          2 |        7.39 |   2689 |
| chain_reverse_char         |     2 | all        | Y       | string_reverse,char_count (!) |          2 |        6.96 |   2623 |
| chain_calc_base            |     2 | all        | Y       | calculator,base_convert (!) |          2 |        9.31 |   2857 |
| chain_cipher_reverse       |     2 | all        | N       | caesar_cipher,string_reverse (!) |          2 |        6.30 |   2574 |
| chain_wc_calc              |     2 | all        | Y       | word_count,calculator (!) |          2 |        9.53 |   2863 |
| chain_calc_temp            |     2 | all        | Y       | calculator,temperature_convert (!) |          2 |       12.59 |   3146 |
| chain_reverse_wc           |     2 | all        | Y       | string_reverse,word_count (!) |          2 |        6.32 |   2559 |
| chain_gcd_base             |     2 | all        | Y       | gcd,base_convert (!) |          2 |       13.88 |   3295 |
| chain_cipher_char          |     2 | all        | Y       | caesar_cipher,char_count (!) |          2 |        9.09 |   2844 |
| chain_base_calc            |     2 | all        | Y       | base_convert,calculator (!) |          2 |        6.32 |   2590 |
| chain_temp_calc            |     2 | all        | Y       | temperature_convert,calculator (!) |          2 |        9.61 |   2851 |
| chain_calc_cipher          |     2 | all        | Y       | calculator,caesar_cipher (!) |          2 |        8.69 |   2811 |
| chain_wc_gcd               |     2 | all        | Y       | word_count,gcd (!)   |          2 |       10.67 |   2969 |
| chain_char_calc            |     2 | all        | Y       | char_count,calculator (!) |          2 |       20.61 |   3875 |
| chain_reverse_cipher       |     2 | all        | Y       | string_reverse,caesar_cipher (!) |          2 |        6.81 |   2621 |
| chain_calc_gcd2            |     2 | all        | Y       | calculator,gcd (!)   |          2 |       10.41 |   2956 |
| chain_temp_gcd             |     2 | all        | Y       | temperature_convert,gcd (!) |          2 |       10.20 |   2952 |
| chain_3step_calc_base_char |     3 | all        | Y       | calculator,base_convert,char_count (!) |          3 |        8.67 |   2874 |
| chain_3step_reverse_char_calc |     3 | all        | Y       | string_reverse,char_count,calculator (!) |          3 |        7.41 |   2723 |
| chain_calc_gcd             |     2 | remove     | Y       | calculator,gcd (!)   |          2 |       15.60 |   2717 |
| chain_temp_base            |     2 | remove     | Y       | temperature_convert,base_convert,base_convert,base_convert (!) |          4 |       21.64 |   6678 |
| chain_reverse_char         |     2 | remove     | Y       | string_reverse,char_count (!) |          2 |        8.97 |   2070 |
| chain_calc_base            |     2 | remove     | N       | none                 |          0 |       22.95 |   1342 |
| chain_cipher_reverse       |     2 | remove     | N       | none                 |          0 |       23.04 |   1374 |
| chain_wc_calc              |     2 | remove     | Y       | none                 |          0 |       23.08 |   1317 |
| chain_calc_temp            |     2 | remove     | Y       | calculator,calculator |          2 |       14.48 |   2589 |
| chain_reverse_wc           |     2 | remove     | Y       | string_reverse,word_count (!) |          2 |        6.08 |   1790 |
| chain_gcd_base             |     2 | remove     | Y       | gcd,base_convert,base_convert (!) |          3 |       17.99 |   4780 |
| chain_cipher_char          |     2 | remove     | Y       | none                 |          0 |       23.10 |   1380 |
| chain_base_calc            |     2 | remove     | Y       | base_convert,calculator |          2 |       17.05 |   3858 |
| chain_temp_calc            |     2 | remove     | Y       | none                 |          0 |       23.04 |   1368 |
| chain_calc_cipher          |     2 | remove     | N       | none                 |          0 |       22.89 |   1347 |
| chain_wc_gcd               |     2 | remove     | Y       | word_count,gcd (!)   |          2 |        7.26 |   1927 |
| chain_char_calc            |     2 | remove     | Y       | char_count,calculator |          2 |       23.21 |   4635 |
| chain_reverse_cipher       |     2 | remove     | Y       | string_reverse,caesar_cipher (!) |          2 |        7.17 |   1890 |
| chain_calc_gcd2            |     2 | remove     | Y       | none                 |          0 |       23.06 |   1340 |
| chain_temp_gcd             |     2 | remove     | N       | none                 |          0 |       23.04 |   1375 |
| chain_3step_calc_base_char |     3 | remove     | Y       | calculator,base_convert,char_count,base_convert,char_count (!) |          5 |       11.75 |   4032 |
| chain_3step_reverse_char_calc |     3 | remove     | Y       | string_reverse,char_count,calculator,calculator (!) |          4 |        8.73 |   3515 |
| chain_calc_gcd             |     2 | logit_mask | Y       | calculator,calculator,calculator,gcd |          4 |        9.87 |   4317 |
| chain_temp_base            |     2 | logit_mask | Y       | temperature_convert,temperature_convert,temperature_convert,base_convert |          4 |       10.71 |   4506 |
| chain_reverse_char         |     2 | logit_mask | Y       | string_reverse,char_count |          2 |        8.01 |   3903 |
| chain_calc_base            |     2 | logit_mask | Y       | calculator,Base_convert,base_convert (!) |          3 |       14.00 |   4808 |
| chain_cipher_reverse       |     2 | logit_mask | Y       | caesar_cipher,str_reverse,string_reverse (!) |          3 |       18.26 |   5408 |
| chain_wc_calc              |     2 | logit_mask | Y       | word_count,计算器,calculator (!) |          3 |       14.80 |   4737 |
| chain_calc_temp            |     2 | logit_mask | Y       | calculator,温度转换,temperature_convert (!) |          3 |       16.48 |   4886 |
| chain_reverse_wc           |     2 | logit_mask | Y       | string_reverse,string_reverse,string_reverse,string_reverse,string_reverse,string_reverse,string_reverse,string_reverse,string_reverse,string_reverse |         10 |       12.80 |   3231 |
| chain_gcd_base             |     2 | logit_mask | Y       | gcd,.base_convert,base_convert (!) |          3 |       20.76 |   5706 |
| chain_cipher_char          |     2 | logit_mask | Y       | caesar_cipher,caesar_cipher,caesar_cipher,char_count |          4 |       12.82 |   4749 |
| chain_base_calc            |     2 | logit_mask | Y       | base_convert,计算器,calculator (!) |          3 |        7.64 |   3976 |
| chain_temp_calc            |     2 | logit_mask | Y       | temperature_convert,计算器,calculator (!) |          3 |       11.73 |   4489 |
| chain_calc_cipher          |     2 | logit_mask | Y       | calculator,ceasar_cipher,caesar_cipher (!) |          3 |        9.32 |   4177 |
| chain_wc_gcd               |     2 | logit_mask | Y       | word_count,gcd       |          2 |       10.00 |   4245 |
| chain_char_calc            |     2 | logit_mask | Y       | char_count,计算器,calculator (!) |          3 |       19.52 |   5335 |
| chain_reverse_cipher       |     2 | logit_mask | N       | string_reverse,string_reverse,string_reverse,caesar_cipher,caesar_cipher,caesar_cipher,caesar_cipher,caesar_cipher,caesar_cipher,caesar_cipher |         10 |       15.69 |  12450 |
| chain_calc_gcd2            |     2 | logit_mask | Y       | calculator,calculator,calculator,gcd |          4 |       12.23 |   4614 |
| chain_temp_gcd             |     2 | logit_mask | Y       | temperature_convert,gc,gcd (!) |          3 |       11.27 |   4474 |
| chain_3step_calc_base_char |     3 | logit_mask | Y       | calculator,.base_convert,.char_count,base_convert,char_count (!) |          5 |       10.12 |   4360 |
| chain_3step_reverse_char_calc |     3 | logit_mask | Y       | string_reverse,char_count,calculator |          3 |        9.84 |   5459 |
| chain_calc_gcd             |     2 | desc_mask  | Y       | calculator,gcd (!)   |          2 |        9.77 |   2950 |
| chain_temp_base            |     2 | desc_mask  | Y       | temperature_convert,base_convert (!) |          2 |        6.38 |   2662 |
| chain_reverse_char         |     2 | desc_mask  | Y       | string_reverse,char_count (!) |          2 |        6.40 |   2646 |
| chain_calc_base            |     2 | desc_mask  | Y       | calculator,base_convert (!) |          2 |       10.85 |   3070 |
| chain_cipher_reverse       |     2 | desc_mask  | Y       | caesar_cipher,string_reverse,caesar_cipher,string_reverse (!) |          4 |       16.81 |   4479 |
| chain_wc_calc              |     2 | desc_mask  | Y       | word_count,calculator (!) |          2 |       10.26 |   2980 |
| chain_calc_temp            |     2 | desc_mask  | Y       | calculator,temperature_convert (!) |          2 |       11.10 |   3055 |
| chain_reverse_wc           |     2 | desc_mask  | Y       | string_reverse,word_count (!) |          2 |        5.86 |   2580 |
| chain_gcd_base             |     2 | desc_mask  | Y       | gcd,base_convert (!) |          2 |       16.45 |   3588 |
| chain_cipher_char          |     2 | desc_mask  | Y       | caesar_cipher,char_count (!) |          2 |        9.88 |   2965 |
| chain_base_calc            |     2 | desc_mask  | Y       | base_convert,calculator (!) |          2 |        8.18 |   2833 |
| chain_temp_calc            |     2 | desc_mask  | Y       | temperature_convert,calculator,calculator (!) |          3 |        9.07 |   4202 |
| chain_calc_cipher          |     2 | desc_mask  | Y       | calculator,caesar_cipher (!) |          2 |        8.78 |   2868 |
| chain_wc_gcd               |     2 | desc_mask  | Y       | word_count,gcd (!)   |          2 |        9.32 |   2908 |
| chain_char_calc            |     2 | desc_mask  | Y       | char_count,calculator (!) |          2 |       13.00 |   3252 |
| chain_reverse_cipher       |     2 | desc_mask  | Y       | string_reverse,caesar_cipher (!) |          2 |        7.59 |   2758 |
| chain_calc_gcd2            |     2 | desc_mask  | Y       | calculator,gcd (!)   |          2 |       13.41 |   3297 |
| chain_temp_gcd             |     2 | desc_mask  | Y       | temperature_convert,gcd (!) |          2 |        9.96 |   2989 |
| chain_3step_calc_base_char |     3 | desc_mask  | Y       | calculator,base_convert,char_count (!) |          3 |        8.91 |   2967 |
| chain_3step_reverse_char_calc |     3 | desc_mask  | Y       | string_reverse,char_count,calculator (!) |          3 |        7.55 |   2812 |

## Latency Analysis

### all
- Mean: 9.487s
- Median: 8.991s
- P90: 13.882s
- Min: 6.084s
- Max: 20.777s

### remove
- Mean: 16.794s
- Median: 19.196s
- P90: 23.088s
- Min: 6.036s
- Max: 23.210s

### logit_mask
- Mean: 12.899s
- Median: 12.037s
- P90: 19.163s
- Min: 7.636s
- Max: 20.761s

### desc_mask
- Mean: 9.962s
- Median: 9.615s
- P90: 16.451s
- Min: 5.848s
- Max: 17.536s

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
