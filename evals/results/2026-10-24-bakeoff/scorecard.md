# Bake-off scorecard

| model | judge_score | judge_category_hit | judge_quebec_accept | grammar_score | quebec_score | conjugation_score | genders_score | open_gen_score | explain_score | json_valid_rate | judge_latency_p50 | judge_latency_p90 | decode_tok_s | prefill_tok_s | load_s | resident_gb | swap_before_mb | swap_after_mb | free_pct_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma4:12b-it-qat | 0.846 | 0.84 | 0.75 | 0.933 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 7.0 | 8.97 | 22.2 | 53.6 | 0.01 | 7.67 | 13637.12 | 22672.38 | 13 |
| qwen3.5:9b | 0.744 | 0.833 | 0.25 | 0.933 | 0.857 | 0.75 | 1.0 | 1.0 | 1.0 | 0.988 | 5.06 | 6.44 | 24.4 | 15.3 | 6.29 | 7.76 | 22665.62 | 21460.0 | 14 |
| ministral-3:8b | 0.744 | 0.68 | 0.5 | 0.8 | 0.929 | 0.9 | 1.0 | 0.8 | 0.889 | 1.0 | 5.45 | 7.66 | 27.6 | 226.8 | 4.84 | 6.22 | 21436.81 | 15320.12 | 16 |
| qwen3.5:4b | 0.769 | 0.72 | 0.5 | 0.667 | 0.643 | 0.8 | 1.0 | 1.0 | 0.889 | 0.975 | 3.5 | 4.5 | 45.2 | 53.2 | 2.52 | 4.07 | 15315.62 | 20539.38 | 25 |
