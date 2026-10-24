import asyncio, json, platform, resource, sys, time
from importlib.metadata import version
import numpy as np, onnxruntime as ort, soundfile as sf
from kokoro_onnx import Kokoro

VOICE, LANG, REPS, WARMUP = "ff_siwis", "fr-fr", 10, 3
RUNS = [(k, 1.0) for k in "ABCD"] + [("A", 0.75), ("C", 0.75)]
samples = json.load(open("samples.json"))["samples"]

t0 = time.perf_counter()
kokoro = Kokoro("/models/kokoro-v1.0.onnx", "/models/voices-v1.0.bin")
load_s = time.perf_counter() - t0

async def synth(text, speed):
    t = time.perf_counter(); first = None; chunks = []
    async for audio, sr in kokoro.create_stream(text, voice=VOICE, speed=speed, lang=LANG):
        if first is None: first = time.perf_counter() - t
        chunks.append(audio)
    total = time.perf_counter() - t
    return np.concatenate(chunks), sr, first, total, len(chunks)

env = dict(backend="docker-onnx", machine=platform.machine(), providers=ort.get_available_providers(),
           onnxruntime=version("onnxruntime"), kokoro_onnx=version("kokoro-onnx"), python=sys.version.split()[0],
           model="kokoro-v1.0.onnx (fp32)", load_s=load_s)
print(env, flush=True)
for _ in range(WARMUP): asyncio.run(synth(samples["B"]["text"], 1.0))

results = []
for key, speed in RUNS:
    rows = []
    for i in range(REPS):
        audio, sr, first, total, n = asyncio.run(synth(samples[key]["text"], speed))
        rows.append(dict(synth_s=total, first_chunk_s=first, audio_s=len(audio) / sr, chunks=n))
        if i == 0: sf.write(f"results/audio/{key}_{speed}_onnx.wav", audio, sr, subtype="PCM_16")
    results.append(dict(sample=key, speed=speed, runs=rows))
    print(key, speed, "median synth", sorted(r["synth_s"] for r in rows)[REPS // 2], flush=True)

env["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB on Linux
json.dump(dict(env=env, results=results), open("results/onnx.json", "w"), indent=2)
