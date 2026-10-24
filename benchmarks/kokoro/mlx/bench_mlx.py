import json, platform, resource, sys, time
from importlib.metadata import version
import mlx.core as mx, numpy as np, soundfile as sf
from mlx.utils import tree_flatten
from mlx_audio.tts.utils import load_model

VOICE, REPO, REPS, WARMUP = "ff_siwis", "mlx-community/Kokoro-82M-bf16", 10, 3
RUNS = [(k, 1.0) for k in "ABCD"] + [("A", 0.75), ("C", 0.75)]
samples = json.load(open("../samples.json"))["samples"]

t0 = time.perf_counter()
model = load_model(REPO)
load_s = time.perf_counter() - t0

def synth(text, speed):
    t = time.perf_counter(); first = None; chunks = []
    for r in model.generate(text=text, voice=VOICE, speed=speed, lang_code="f"):
        a = np.array(r.audio)  # forces lazy MLX evaluation before timestamping
        if first is None: first = time.perf_counter() - t
        chunks.append(a.reshape(-1))
    total = time.perf_counter() - t
    return np.concatenate(chunks), 24000, first, total, len(chunks)

dtypes = sorted({str(p.dtype) for _, p in tree_flatten(model.parameters())})
env = dict(backend="native-mlx", machine=platform.machine(), device=str(mx.default_device()),
           mlx=version("mlx"), mlx_audio=version("mlx-audio"), python=sys.version.split()[0],
           model=REPO, weight_dtypes=dtypes, load_s=load_s)
print(env, flush=True)
t = time.perf_counter(); synth(samples["B"]["text"], 1.0); env["first_synth_s"] = time.perf_counter() - t
for _ in range(WARMUP - 1): synth(samples["B"]["text"], 1.0)

mx.reset_peak_memory()
results = []
for key, speed in RUNS:
    rows = []
    for i in range(REPS):
        audio, sr, first, total, n = synth(samples[key]["text"], speed)
        rows.append(dict(synth_s=total, first_chunk_s=first, audio_s=len(audio) / sr, chunks=n))
        if i == 0: sf.write(f"../results/audio/{key}_{speed}_mlx.wav", audio, sr, subtype="PCM_16")
    results.append(dict(sample=key, speed=speed, runs=rows))
    print(key, speed, "median synth", sorted(r["synth_s"] for r in rows)[REPS // 2], flush=True)

env["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024  # bytes on macOS
env["peak_metal_mb"] = mx.get_peak_memory() / 1024 / 1024
json.dump(dict(env=env, results=results), open("../results/mlx.json", "w"), indent=2)
