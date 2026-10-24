"""Spike 4: Metal memory and latency vs mx.set_cache_limit.

Run: uv run python scripts/measure_memory.py

Each cache-limit setting runs in a fresh subprocess so peak/active numbers are not polluted.
"""

from __future__ import annotations

import json
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

SAMPLES = Path(__file__).resolve().parents[3] / "benchmarks/kokoro/samples.json"
LIMITS: list[int | None] = [None, 1024, 512, 256]
REPS = 5
MB = 1024 * 1024


def worker(limit: int | None) -> None:
    import mlx.core as mx

    from frenchia_tts.config import Settings
    from frenchia_tts.engine import KokoroEngine

    eng = KokoroEngine(Settings(mlx_cache_limit_mb=limit))
    eng._load()  # includes warm-up synthesis
    samples = json.loads(SAMPLES.read_text())["samples"]
    for _ in range(2):  # extra warm-up over a long sample
        eng._synth(samples["D"]["text"], "ff_siwis", 1.0)
    mx.reset_peak_memory()
    out: dict[str, Any] = {"median_s": {}}
    for key, s in samples.items():
        times = []
        for _ in range(REPS):
            t = time.perf_counter()
            eng._synth(s["text"], "ff_siwis", 1.0)
            times.append(time.perf_counter() - t)
        out["median_s"][key] = statistics.median(times)
    out["peak_mb"] = mx.get_peak_memory() / MB
    out["active_mb"] = mx.get_active_memory() / MB
    out["cache_mb"] = mx.get_cache_memory() / MB
    out["rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / MB  # bytes on macOS
    print("RESULT " + json.dumps(out))


def main() -> None:
    rows = []
    for limit in LIMITS:
        arg = "none" if limit is None else str(limit)
        p = subprocess.run(
            [sys.executable, __file__, "--worker", arg], capture_output=True, text=True, check=True
        )
        line = next(ln for ln in p.stdout.splitlines() if ln.startswith("RESULT "))
        rows.append((arg, json.loads(line[7:])))
    keys = list(rows[0][1]["median_s"])
    heads = [f"{k} median s" for k in keys] + ["total vs none", "peak Metal MB"]
    heads += ["active Metal MB", "RSS MB"]
    print("| cache limit | " + " | ".join(heads) + " |")
    print("|---" * (len(heads) + 1) + "|")
    base = sum(rows[0][1]["median_s"].values())
    for arg, r in rows:
        tot = sum(r["median_s"].values())
        cells = " | ".join(f"{r['median_s'][k]:.3f}" for k in keys)
        print(
            f"| {arg} | {cells} | {tot / base - 1:+.1%} | {r['peak_mb']:.0f} | "
            f"{r['active_mb']:.0f} | {r['rss_mb']:.0f} |"
        )


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(None if sys.argv[2] == "none" else int(sys.argv[2]))
    else:
        main()
