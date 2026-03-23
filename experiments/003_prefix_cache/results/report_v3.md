# Experiment 003 (v3): Prefix Cache Validation — Results

Generated: 2026-03-22 17:52:13

50 tools, 10 tools removed/masked per task

## Summary

| Strategy | Runs | Accuracy | Avg Latency | Avg TTFT | Cache Hit Rate | Avg Input Tok | Avg Output Tok |
|----------|------|----------|-------------|----------|----------------|---------------|----------------|
| all        |    3 |   83.3% |       12.34s |   0.683s |         99.5% |         11308 |            444 |
| remove     |    3 |   80.0% |       12.32s |   0.650s |         99.5% |          8304 |            457 |
| logit_mask |    3 |   88.3% |       17.33s |   0.650s |         98.8% |         13707 |            638 |
| desc_mask  |    3 |   83.3% |       12.17s |   0.652s |         98.9% |         10674 |            444 |

## TTFT Analysis (Time to First Token)

### all
- Mean: 0.683s
- Median: 0.660s
- P90: 0.813s
- Min: 0.564s, Max: 1.083s
- Count: 139 turns

### remove
- Mean: 0.650s
- Median: 0.642s
- P90: 0.725s
- Min: 0.371s, Max: 0.837s
- Count: 122 turns

### logit_mask
- Mean: 0.650s
- Median: 0.630s
- P90: 0.700s
- Min: 0.567s, Max: 1.407s
- Count: 161 turns

### desc_mask
- Mean: 0.652s
- Median: 0.638s
- P90: 0.710s
- Min: 0.565s, Max: 1.024s
- Count: 129 turns

## Prefix Cache Metrics

| Strategy | Run | Queries (delta) | Hits (delta) | Hit Rate |
|----------|-----|-----------------|--------------|----------|
| all        |   1 |         706,223 |      702,752 |   99.5% |
| all        |   2 |         658,459 |      655,152 |   99.5% |
| all        |   3 |         667,393 |      664,064 |   99.5% |
| remove     |   1 |         495,056 |      492,640 |   99.5% |
| remove     |   2 |         497,687 |      495,248 |   99.5% |
| remove     |   3 |         492,588 |      490,176 |   99.5% |
| logit_mask |   1 |         867,299 |      855,584 |   98.6% |
| logit_mask |   2 |         818,303 |      811,712 |   99.2% |
| logit_mask |   3 |         815,371 |      804,208 |   98.6% |
| desc_mask  |   1 |         557,392 |      552,864 |   99.2% |
| desc_mask  |   2 |         645,179 |      635,280 |   98.5% |
| desc_mask  |   3 |         610,364 |      605,072 |   99.1% |

## Per-Task Results (Last Run)

| Task ID | Strategy | Correct | Steps | Latency | Avg TTFT | Tokens |
|---------|----------|---------|-------|---------|----------|--------|
| chain4_calc_bin_char_power          | all        | N       |  4/4 |    8.07s |   0.694s |   9871 |
| chain4_reverse_len_mod_even         | all        | Y       |  4/4 |   12.07s |   0.840s |  10140 |
| chain4_wc_power_base_upper          | all        | Y       |  4/4 |    9.46s |   0.710s |  10000 |
| chain4_caesar_reverse_len_calc      | all        | Y       |  4/4 |    9.19s |   0.797s |   9946 |
| chain5_calc_gcd_bin_char_power      | all        | Y       |  5/5 |   11.69s |   0.698s |  10234 |
| chain4_temp_round_mod_abs           | all        | Y       |  4/4 |   12.75s |   0.659s |  25071 |
| chain5_reverse_upper_len_lcm_bin    | all        | Y       |  5/5 |    9.54s |   0.663s |  10022 |
| chain4_calc_floor_gcd_even          | all        | Y       |  4/4 |   13.30s |   0.762s |  10306 |
| chain4_lower_replace_char_calc      | all        | N       |  0/4 |   25.66s |   0.715s |   5654 |
| chain5_calc_mod_power_sumdig_even   | all        | N       |  5/5 |    9.76s |   0.616s |  10046 |
| chain4_sort_first3_upper_len        | all        | Y       |  4/4 |   16.50s |   0.618s |  10542 |
| chain5_wc_gcd_power_bin_char        | all        | Y       |  5/5 |   10.87s |   0.672s |  10150 |
| chain4_unique_len_max_round         | all        | Y       |  4/4 |   15.85s |   0.682s |  10493 |
| chain4_calc_base_lower_len          | all        | Y       |  4/4 |   13.05s |   0.709s |  10267 |
| chain5_temp_calc_mod_power_sumdig   | all        | Y       |  5/5 |   11.14s |   0.656s |  29602 |
| chain4_repeat_len_floor_bin         | all        | Y       |  4/4 |   11.48s |   0.605s |  10151 |
| chain5_caesar_char_lcm_mod_even     | all        | Y       |  5/5 |   10.98s |   0.647s |  10149 |
| chain4_slice_reverse_upper_len      | all        | N       |  4/4 |   12.56s |   0.621s |  10237 |
| chain5_calc_pct_round_floor_bin     | all        | Y       |  5/5 |   11.05s |   0.633s |  10157 |
| chain6_reverse_len_power_bin_char_calc | all        | Y       |  6/6 |   10.19s |   0.738s |  10143 |
| chain4_calc_bin_char_power          | remove     | N       |  4/4 |    8.30s |   0.736s |   8255 |
| chain4_reverse_len_mod_even         | remove     | Y       |  4/4 |    9.03s |   0.688s |   8322 |
| chain4_wc_power_base_upper          | remove     | N       |  4/4 |    8.61s |   0.682s |   8316 |
| chain4_caesar_reverse_len_calc      | remove     | Y       |  4/4 |    7.75s |   0.667s |   8230 |
| chain5_calc_gcd_bin_char_power      | remove     | Y       |  5/5 |    9.66s |   0.626s |   8468 |
| chain4_temp_round_mod_abs           | remove     | Y       |  4/4 |   11.54s |   0.656s |  20821 |
| chain5_reverse_upper_len_lcm_bin    | remove     | Y       |  5/5 |    9.58s |   0.756s |   8408 |
| chain4_calc_floor_gcd_even          | remove     | Y       |  4/4 |   12.94s |   0.613s |   8682 |
| chain4_lower_replace_char_calc      | remove     | N       |  5/4 |   34.58s |   0.630s |  25570 |
| chain5_calc_mod_power_sumdig_even   | remove     | N       |  5/5 |    9.47s |   0.616s |   8406 |
| chain4_sort_first3_upper_len        | remove     | Y       |  4/4 |   23.48s |   0.667s |   9508 |
| chain5_wc_gcd_power_bin_char        | remove     | Y       |  5/5 |   12.38s |   0.722s |   8662 |
| chain4_unique_len_max_round         | remove     | Y       |  4/4 |    8.49s |   0.675s |   8285 |
| chain4_calc_base_lower_len          | remove     | Y       |  4/4 |   10.41s |   0.646s |   8465 |
| chain5_temp_calc_mod_power_sumdig   | remove     | Y       |  5/5 |   12.60s |   0.642s |   8664 |
| chain4_repeat_len_floor_bin         | remove     | Y       |  4/4 |   12.68s |   0.623s |   8639 |
| chain5_caesar_char_lcm_mod_even     | remove     | Y       |  5/5 |    9.50s |   0.597s |   8421 |
| chain4_slice_reverse_upper_len      | remove     | N       |  4/4 |   11.96s |   0.631s |   8571 |
| chain5_calc_pct_round_floor_bin     | remove     | Y       |  5/5 |    9.38s |   0.643s |   8415 |
| chain6_reverse_len_power_bin_char_calc | remove     | Y       |  6/6 |    9.94s |   0.622s |   8525 |
| chain4_calc_bin_char_power          | logit_mask | N       |  4/4 |    8.15s |   0.624s |   9871 |
| chain4_reverse_len_mod_even         | logit_mask | Y       | 30/4 |   43.55s |   0.662s |  18954 |
| chain4_wc_power_base_upper          | logit_mask | Y       |  4/4 |    9.83s |   0.633s |  10022 |
| chain4_caesar_reverse_len_calc      | logit_mask | Y       |  4/4 |   10.06s |   0.637s |  24596 |
| chain5_calc_gcd_bin_char_power      | logit_mask | Y       |  5/5 |   11.87s |   0.616s |  10242 |
| chain4_temp_round_mod_abs           | logit_mask | Y       |  4/4 |   11.54s |   0.625s |  24891 |
| chain5_reverse_upper_len_lcm_bin    | logit_mask | Y       |  5/5 |    9.19s |   0.595s |  10006 |
| chain4_calc_floor_gcd_even          | logit_mask | Y       |  8/4 |   18.10s |   0.644s |  16024 |
| chain4_lower_replace_char_calc      | logit_mask | Y       |  4/4 |   15.47s |   0.633s |  10479 |
| chain5_calc_mod_power_sumdig_even   | logit_mask | N       | 19/5 |   39.94s |   0.703s |  58903 |
| chain4_sort_first3_upper_len        | logit_mask | Y       |  5/4 |   32.63s |   0.651s |  17569 |
| chain5_wc_gcd_power_bin_char        | logit_mask | Y       |  5/5 |   15.28s |   0.614s |  10522 |
| chain4_unique_len_max_round         | logit_mask | Y       |  4/4 |    8.33s |   0.660s |   9883 |
| chain4_calc_base_lower_len          | logit_mask | Y       |  4/4 |    8.73s |   0.604s |   9939 |
| chain5_temp_calc_mod_power_sumdig   | logit_mask | Y       |  5/5 |   11.13s |   0.610s |  10152 |
| chain4_repeat_len_floor_bin         | logit_mask | Y       |  4/4 |   11.68s |   0.652s |  10151 |
| chain5_caesar_char_lcm_mod_even     | logit_mask | Y       | 31/5 |   29.98s |   0.606s |  11819 |
| chain4_slice_reverse_upper_len      | logit_mask | Y       |  0/4 |   25.67s |   0.590s |   5644 |
| chain5_calc_pct_round_floor_bin     | logit_mask | Y       |  5/5 |   11.19s |   0.635s |  10171 |
| chain6_reverse_len_power_bin_char_calc | logit_mask | Y       |  6/6 |   10.34s |   0.629s |  10145 |
| chain4_calc_bin_char_power          | desc_mask  | N       |  4/4 |    8.23s |   0.652s |  10051 |
| chain4_reverse_len_mod_even         | desc_mask  | Y       |  4/4 |    8.93s |   0.661s |  10088 |
| chain4_wc_power_base_upper          | desc_mask  | Y       |  4/4 |    9.56s |   0.622s |  10188 |
| chain4_caesar_reverse_len_calc      | desc_mask  | Y       |  4/4 |   10.60s |   0.653s |  25128 |
| chain5_calc_gcd_bin_char_power      | desc_mask  | Y       |  5/5 |    8.78s |   0.592s |  10186 |
| chain4_temp_round_mod_abs           | desc_mask  | Y       |  4/4 |   12.01s |   0.651s |  25401 |
| chain5_reverse_upper_len_lcm_bin    | desc_mask  | Y       |  5/5 |    9.64s |   0.656s |  10202 |
| chain4_calc_floor_gcd_even          | desc_mask  | Y       |  4/4 |   15.67s |   0.621s |  10706 |
| chain4_lower_replace_char_calc      | desc_mask  | N       |  4/4 |   20.56s |   0.647s |  11083 |
| chain5_calc_mod_power_sumdig_even   | desc_mask  | N       |  5/5 |    9.76s |   0.611s |  10226 |
| chain4_sort_first3_upper_len        | desc_mask  | Y       |  4/4 |   14.56s |   0.684s |  10556 |
| chain5_wc_gcd_power_bin_char        | desc_mask  | Y       |  5/5 |   11.15s |   0.621s |  10352 |
| chain4_unique_len_max_round         | desc_mask  | Y       |  4/4 |   14.81s |   0.637s |  10599 |
| chain4_calc_base_lower_len          | desc_mask  | Y       |  4/4 |    9.94s |   0.684s |  10199 |
| chain5_temp_calc_mod_power_sumdig   | desc_mask  | Y       |  5/5 |   13.09s |   0.724s |  10468 |
| chain4_repeat_len_floor_bin         | desc_mask  | Y       |  4/4 |   11.34s |   0.631s |  10305 |
| chain5_caesar_char_lcm_mod_even     | desc_mask  | Y       |  5/5 |   10.77s |   0.665s |  10313 |
| chain4_slice_reverse_upper_len      | desc_mask  | N       |  4/4 |   13.57s |   0.608s |  10495 |
| chain5_calc_pct_round_floor_bin     | desc_mask  | Y       |  5/5 |   10.18s |   0.626s |  10271 |
| chain6_reverse_len_power_bin_char_calc | desc_mask  | Y       |  6/6 |   10.10s |   0.640s |  10323 |

## Token Map (Logit Mask — first 10 tools)

| Tool Name | Token IDs Blocked |
|-----------|-------------------|
| hex_encode | [12371, 17308] |
| hex_decode | [12371, 17308] |
| rot13 | [4640, 5749] |
| ascii_value | [23324, 47120] |
| vowel_count | [85, 76181] |
| consonant_count | [443, 77505] |
| is_palindrome | [285, 374] |
| factorial | [37591, 52962] |
| fibonacci | [75326, 75698] |
| prime_check | [10250, 32338] |