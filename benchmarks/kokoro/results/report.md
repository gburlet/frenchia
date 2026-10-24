# Kokoro-82M French TTS: Docker ONNX CPU vs native MLX

## Environment
- Apple M2 Pro (6P+4E CPU, 16-core GPU), 16 GB, macOS 26.4.1; Docker Desktop VM 10 vCPU / ~7.75 GiB
- Docker ONNX: `{'backend': 'docker-onnx', 'machine': 'aarch64', 'providers': ['AzureExecutionProvider', 'CPUExecutionProvider'], 'onnxruntime': '1.31.0', 'kokoro_onnx': '0.6.1', 'python': '3.12.15', 'model': 'kokoro-v1.0.onnx (fp32)', 'load_s': 1.2748422930017114, 'peak_rss_mb': 1411.65234375}`
- Native MLX: `{'backend': 'native-mlx', 'machine': 'arm64', 'device': 'Device(gpu, 0)', 'mlx': '0.32.4', 'mlx_audio': '0.6.1', 'python': '3.12.13', 'model': 'mlx-community/Kokoro-82M-bf16', 'weight_dtypes': ['mlx.core.float32'], 'load_s': 0.29117829201277345, 'first_synth_s': 6.050360959023237, 'peak_rss_mb': 340.8125, 'peak_metal_mb': 2710.2587366104126}`
- Voice `ff_siwis`, French (espeak-ng G2P in both), 24 kHz, 10 reps/sample after 3 warm-ups, sequential runs.

## Fairness notes
- Same Kokoro v1.0 checkpoint and voice; ONNX is fp32, MLX weight dtypes listed above.
- Chunking differs (ONNX: 510 phonemes; MLX: ~400-char sentence groups). Only sample D is likely affected.
- ONNX uses `create_stream` (trims silence, inserts pauses); MLX uses `generate`. Total times include everything until the last chunk is materialized.

## Performance (median synth seconds; RTF = synth / audio, lower is better)

| Sample | Speed | Chars | Audio (s) ONNX / MLX | Docker ONNX median | Docker RTF | MLX median | MLX RTF | MLX speedup |
|---|---|---|---|---|---|---|---|---|
| A short | 1.0 | 36 | 1.96 / 2.55 | 0.754 | 0.384 | 0.132 | 0.052 | 5.72x |
| B two sentences | 1.0 | 127 | 7.19 / 7.80 | 1.825 | 0.254 | 0.394 | 0.051 | 4.63x |
| C medium | 1.0 | 292 | 15.45 / 15.97 | 3.641 | 0.236 | 0.776 | 0.049 | 4.69x |
| D long | 1.0 | 649 | 33.52 / 34.40 | 7.060 | 0.211 | 1.703 | 0.050 | 4.15x |
| A short | 0.75 | 36 | 2.73 / 3.40 | 0.911 | 0.333 | 0.169 | 0.050 | 5.40x |
| C medium | 0.75 | 292 | 21.63 / 22.27 | 4.287 | 0.198 | 1.060 | 0.048 | 4.04x |

## Spread and time to first chunk

| Sample | Speed | ONNX mean / p95 / sd | MLX mean / p95 / sd | ONNX first chunk | MLX first chunk | chunks ONNX / MLX |
|---|---|---|---|---|---|---|
| A short | 1.0 | 0.756 / 0.796 / 0.026 | 0.136 / 0.174 / 0.013 | 0.754 | 0.126 | 1 / 1 |
| B two sentences | 1.0 | 1.855 / 2.143 / 0.154 | 0.393 / 0.405 / 0.007 | 1.825 | 0.377 | 1 / 1 |
| C medium | 1.0 | 3.700 / 4.610 / 0.378 | 0.784 / 0.810 / 0.014 | 3.641 | 0.758 | 1 / 1 |
| D long | 1.0 | 7.137 / 7.950 / 0.468 | 1.712 / 1.775 / 0.025 | 3.807 | 0.919 | 2 / 2 |
| A short | 0.75 | 1.051 / 1.704 / 0.258 | 0.170 / 0.178 / 0.003 | 0.911 | 0.161 | 1 / 1 |
| C medium | 0.75 | 4.310 / 4.636 / 0.182 | 1.056 / 1.095 / 0.028 | 4.286 | 1.042 | 1 / 1 |

Neither backend is streamed over HTTP here (in-process test); 'first chunk' is the time until the first generator chunk is materialized.

## Cold start and memory

- Model load: ONNX 1.27s, MLX 0.29s (MLX first synth: 6.05s)
- Peak RSS: ONNX 1412 MB (container process), MLX 341 MB (+ 2710 MB Metal peak)

## Listen (results/audio)

Paired files: `{A,B,C,D}_1.0_{onnx,mlx}.wav` and `{A,C}_0.75_{onnx,mlx}.wav`. Rate each 1-5 for both backends:
- Pronunciation overall; liaison (*des amis*, *des articles*, *des idées*); nasals (*bonjour*, *pain*, *comment*, *maintenant*)
- Elisions (*aujourd'hui*, *j'ai*, *j'essaie*, *l'occasion*); Quebec words (*souper*, *balados*)
- Pauses at punctuation / sentence boundaries; voice consistency across chunks (sample D)
- Does 0.75 speed stay clean or get artifacts?

Quality is not judged in this report; it needs your ears.

## Caveats

- Audio durations differ between backends (e.g. sample A: ONNX 1.96 s vs MLX 2.55 s). kokoro-onnx trims silence and the two stacks may phonemize or pause slightly differently, so RTF is not perfectly like-for-like. Wall-clock time is the number that matters for the app, and the gap is far larger than this difference.
- MLX 'first synth' (6.05 s) includes a one-time voice file download and Metal warm-up; subsequent runs are cached. The MLX weights loaded as float32, matching the ONNX fp32 model.
- MLX logs 'Chunking logic not yet implemented' for French. Sample D produced 2 chunks on both backends and ~34 s of audio, so no obvious truncation, but listen to the end of D to confirm.
- Peak memory is per-process: ONNX measured inside the container (RSS), MLX on the host (RSS plus Metal peak). The Docker VM has a fixed 7.75 GiB budget.
