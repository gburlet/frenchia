# Memory and latency vs MLX cache limit (Spike 4)

M2 Pro 16 GB, `mlx-community/Kokoro-82M-bf16`, `ff_siwis`, samples A-D from
`benchmarks/kokoro/samples.json`, 5 reps each after warm-up. Each limit runs in a fresh process
(`uv run python scripts/measure_memory.py`). Times are medians in seconds (sample A=36 chars ... D=649 chars).

## Run 2 (final; the "none" row was hit by system contention, ignore its latency)

| cache limit | A median s | B median s | C median s | D median s | total vs none | peak Metal MB | active Metal MB | RSS MB |
|---|---|---|---|---|---|---|---|---|
| none | 0.262 | 1.050 | 2.824 | 6.215 | +0.0% | 2513 | 313 | 373 |
| 1024 | 0.139 | 0.427 | 0.950 | 2.419 | -62.0% | 2513 | 313 | 412 |
| 512 | 0.132 | 0.412 | 0.990 | 1.944 | -66.4% | 2513 | 313 | 414 |
| 256 | 0.133 | 0.422 | 0.893 | 1.984 | -66.8% | 2513 | 313 | 436 |

## Run 1 (quiet machine)

| cache limit | A | B | C | D | total vs none | peak Metal MB | active Metal MB | RSS MB |
|---|---|---|---|---|---|---|---|---|
| none | 0.133 | 0.411 | 0.888 | 1.918 | +0.0% | 2513 | 313 | 424 |
| 1024 | 0.133 | 0.411 | 0.868 | 1.895 | -1.3% | 2513 | 313 | 461 |
| 512 | 0.133 | 0.405 | 0.865 | 1.875 | -2.2% | 2513 | 313 | 461 |
| 256 | 0.130 | 0.400 | 0.862 | 1.890 | -2.1% | 2513 | 313 | 465 |

## Conclusion

- Limiting the buffer cache costs no latency (every limit is within noise, 2% faster or slower, far
  inside the 5% budget). Even 256 MB is enough for this model.
- Peak Metal (~2.5 GB, transient activations during synthesis) is identical for all limits, so the
  cache limit does not lower the peak. It only bounds how much freed memory stays cached afterwards.
- Resident state is small: ~313 MB active Metal after synthesis, RSS ~0.4 GB.
- **Default: `TTS_MLX_CACHE_LIMIT_MB=256`** (smallest limit costing under 5% latency). Set `none` to disable.
