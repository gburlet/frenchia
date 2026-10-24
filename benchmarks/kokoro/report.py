import json, statistics as st
from pathlib import Path

def load(name):
    p = Path(f"results/{name}.json")
    return json.loads(p.read_text()) if p.exists() else None

def stats(runs):
    t = sorted(r["synth_s"] for r in runs); a = st.mean(r["audio_s"] for r in runs)
    med = st.median(t)
    return dict(med=med, mean=st.mean(t), p95=t[min(len(t) - 1, int(0.95 * len(t)))], sd=st.pstdev(t),
                audio=a, rtf=med / a, xrt=a / med, ttfc=st.median(r["first_chunk_s"] for r in runs),
                chunks=runs[0]["chunks"])

D, M = load("onnx"), load("mlx")
idx = lambda d: {(r["sample"], r["speed"]): stats(r["runs"]) for r in d["results"]}
di, mi = idx(D), idx(M)
samples = json.load(open("samples.json"))["samples"]
names = {"A": "A short", "B": "B two sentences", "C": "C medium", "D": "D long"}

L = ["# Kokoro-82M French TTS: Docker ONNX CPU vs native MLX", "",
     "## Environment", "- Apple M2 Pro (6P+4E CPU, 16-core GPU), 16 GB, macOS 26.4.1; Docker Desktop VM 10 vCPU / ~7.75 GiB",
     f"- Docker ONNX: `{D['env']}`", f"- Native MLX: `{M['env']}`", "- Voice `ff_siwis`, French (espeak-ng G2P in both), 24 kHz, 10 reps/sample after 3 warm-ups, sequential runs.",
     "", "## Fairness notes",
     "- Same Kokoro v1.0 checkpoint and voice; ONNX is fp32, MLX weight dtypes listed above.",
     "- Chunking differs (ONNX: 510 phonemes; MLX: ~400-char sentence groups). Only sample D is likely affected.",
     "- ONNX uses `create_stream` (trims silence, inserts pauses); MLX uses `generate`. Total times include everything until the last chunk is materialized.",
     "", "## Performance (median synth seconds; RTF = synth / audio, lower is better)", "",
     "| Sample | Speed | Chars | Audio (s) ONNX / MLX | Docker ONNX median | Docker RTF | MLX median | MLX RTF | MLX speedup |",
     "|---|---|---|---|---|---|---|---|---|"]
for (k, sp) in di:
    d, m = di[(k, sp)], mi[(k, sp)]
    L.append(f"| {names[k]} | {sp} | {samples[k]['chars']} | {d['audio']:.2f} / {m['audio']:.2f} | {d['med']:.3f} | {d['rtf']:.3f} | {m['med']:.3f} | {m['rtf']:.3f} | {d['med'] / m['med']:.2f}x |")
L += ["", "## Spread and time to first chunk", "",
      "| Sample | Speed | ONNX mean / p95 / sd | MLX mean / p95 / sd | ONNX first chunk | MLX first chunk | chunks ONNX / MLX |", "|---|---|---|---|---|---|---|"]
for (k, sp) in di:
    d, m = di[(k, sp)], mi[(k, sp)]
    L.append(f"| {names[k]} | {sp} | {d['mean']:.3f} / {d['p95']:.3f} / {d['sd']:.3f} | {m['mean']:.3f} / {m['p95']:.3f} / {m['sd']:.3f} | {d['ttfc']:.3f} | {m['ttfc']:.3f} | {d['chunks']} / {m['chunks']} |")
L += ["", "Neither backend is streamed over HTTP here (in-process test); 'first chunk' is the time until the first generator chunk is materialized.", "",
      "## Cold start and memory", "",
      f"- Model load: ONNX {D['env']['load_s']:.2f}s, MLX {M['env']['load_s']:.2f}s (MLX first synth: {M['env'].get('first_synth_s', float('nan')):.2f}s)",
      f"- Peak RSS: ONNX {D['env']['peak_rss_mb']:.0f} MB (container process), MLX {M['env']['peak_rss_mb']:.0f} MB (+ {M['env']['peak_metal_mb']:.0f} MB Metal peak)",
      "", "## Listen (results/audio)", "",
      "Paired files: `{A,B,C,D}_1.0_{onnx,mlx}.wav` and `{A,C}_0.75_{onnx,mlx}.wav`. Rate each 1-5 for both backends:",
      "- Pronunciation overall; liaison (*des amis*, *des articles*, *des idées*); nasals (*bonjour*, *pain*, *comment*, *maintenant*)",
      "- Elisions (*aujourd'hui*, *j'ai*, *j'essaie*, *l'occasion*); Quebec words (*souper*, *balados*)",
      "- Pauses at punctuation / sentence boundaries; voice consistency across chunks (sample D)",
      "- Does 0.75 speed stay clean or get artifacts?", "",
      "Quality is not judged in this report; it needs your ears."]
Path("results/report.md").write_text("\n".join(L) + "\n")
print("\n".join(L))

with open("results/report.md", "a") as f:
    f.write("""
## Caveats

- Audio durations differ between backends (e.g. sample A: ONNX 1.96 s vs MLX 2.55 s). kokoro-onnx trims silence and the two stacks may phonemize or pause slightly differently, so RTF is not perfectly like-for-like. Wall-clock time is the number that matters for the app, and the gap is far larger than this difference.
- MLX 'first synth' (6.05 s) includes a one-time voice file download and Metal warm-up; subsequent runs are cached. The MLX weights loaded as float32, matching the ONNX fp32 model.
- MLX logs 'Chunking logic not yet implemented' for French. Sample D produced 2 chunks on both backends and ~34 s of audio, so no obvious truncation, but listen to the end of D to confirm.
- Peak memory is per-process: ONNX measured inside the container (RSS), MLX on the host (RSS plus Metal peak). The Docker VM has a fixed 7.75 GiB budget.
""")
