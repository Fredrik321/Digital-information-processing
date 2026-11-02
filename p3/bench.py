"""Timing and memory evidence for one storage choice, plus one implementation fix.

    python bench.py      # writes outputs/bench/bench.json and bench.md

Storage: how should the pipeline hold the 811 decoded images?
  jpeg      decode the JPEG files every time (what P1/P2 did)
  npy       one uncompressed .npy cache (122 MB), loaded fully
  npy_mmap  the same .npy, memory-mapped read-only
Each runs two workloads, in a fresh subprocess per repeat so the peak memory
belongs to that measurement alone:
  all       use every image (per-channel mean over the whole dataset)
  subset    fetch the 14 images the test pipeline uses
Implementation: the Huffman bit packer from P2 (unbounded accumulator)
against the P3 version (masked accumulator), on the same input.

Timings are warm-cache: one discarded warm-up run, then REPEATS measured runs.
tracemalloc slows every Python allocation, so times and RSS come from untraced
runs, and the heap peak from one extra traced run.
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections import Counter
from pathlib import Path

import numpy as np

from common import HERE, environment_info, load_config, peak_rss_bytes, atomic_write_json, atomic_write_text
import manifest
import pipeline
import validate

CACHE = HERE / "cache" / "dataset_uint8.npy"
OUT = HERE / "outputs" / "bench"
REPEATS = 5
METHODS = ("jpeg", "npy", "npy_mmap")
WORKLOADS = ("all", "subset")


def dataset():
    config = load_config(HERE / "config.json")
    paths = [e["path"] for e in manifest.read(config["manifest"])]
    subset = pipeline.select_subset(paths, config["subset"]["per_class"], config["seed"],
                                    config["subset"]["include"])
    return config, paths, subset


def ensure_cache(config, paths):
    """Build the .npy cache if needed, and check it against the decoded-pixel
    digest so a stale or damaged cache is never benchmarked."""
    schema = validate.load_schema(config["schema"])
    expected = validate.validate_all(config["dataset_root"], paths, schema)
    if CACHE.exists():
        import hashlib
        if hashlib.sha256(np.load(CACHE, mmap_mode="r").tobytes()).hexdigest() == expected:
            return expected
    root = Path(config["dataset_root"])
    arr = np.stack([validate.load_image(root / p, schema) for p in paths])
    CACHE.parent.mkdir(exist_ok=True)
    np.save(CACHE, arr)
    return expected


def worker(method, workload, trace):
    """One measurement. Prints a JSON line for the parent to collect."""
    from PIL import Image
    config, paths, subset = dataset()
    root = Path(config["dataset_root"])
    index = [paths.index(p) for p in subset]
    rss_before = peak_rss_bytes()
    if trace:
        tracemalloc.start()
    t0 = time.perf_counter()
    if method == "jpeg":
        chosen = paths if workload == "all" else subset
        arr = np.empty((len(chosen), 224, 224, 3), dtype=np.uint8)
        for i, rel in enumerate(chosen):
            with Image.open(root / rel) as im:
                arr[i] = np.asarray(im)
    else:
        full = np.load(CACHE, mmap_mode="r" if method == "npy_mmap" else None)
        arr = full if workload == "all" else full[index]
    mean = arr.mean(axis=(0, 1, 2))         # reads every byte of what was fetched
    seconds = time.perf_counter() - t0
    traced = tracemalloc.get_traced_memory()[1] if trace else None
    print(json.dumps({"seconds": seconds, "rss_increase": peak_rss_bytes() - rss_before,
                      "traced_peak": traced, "images": int(arr.shape[0]),
                      "mean": [round(float(m), 4) for m in mean]}))


def run_worker(method, workload, trace=False):
    cmd = [sys.executable, __file__, "--worker", method, workload] + (["--trace"] if trace else [])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def measure_storage():
    results = {}
    for method in METHODS:
        for workload in WORKLOADS:
            run_worker(method, workload)  # warm-up: fills the OS file cache
            runs = [run_worker(method, workload) for _ in range(REPEATS)]
            traced = run_worker(method, workload, trace=True)
            secs = [r["seconds"] for r in runs]
            results[f"{method}/{workload}"] = {
                "method": method, "workload": workload, "images": runs[0]["images"],
                "seconds_median": round(statistics.median(secs), 4),
                "seconds_min": round(min(secs), 4), "seconds_max": round(max(secs), 4),
                "rss_increase_mib_median": round(statistics.median(
                    r["rss_increase"] for r in runs) / 2**20, 1),
                "heap_peak_mib": round(traced["traced_peak"] / 2**20, 1),
                "channel_mean": runs[0]["mean"],
            }
            print(f"{method:9s} {workload:6s} {results[f'{method}/{workload}']}", flush=True)
    return results


def measure_encoder(config, subset):
    from PIL import Image
    from codec import canonical_codes, encode_symbols, encode_symbols_p2, huffman_code_lengths
    root = Path(config["dataset_root"])
    rows = []
    for rel in subset[:3]:
        with Image.open(root / rel) as im:
            raw = np.asarray(im).tobytes()
        codes = canonical_codes(huffman_code_lengths(Counter(raw)))
        row = {"path": rel, "raw_bytes": len(raw)}
        outputs = {}
        for name, fn, repeats in (("p2", encode_symbols_p2, 1), ("p3", encode_symbols, REPEATS)):
            times = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                outputs[name] = fn(raw, codes)
                times.append(time.perf_counter() - t0)
            row[f"{name}_seconds"] = round(statistics.median(times), 4)
            tracemalloc.start()
            fn(raw, codes)
            row[f"{name}_heap_peak_kib"] = round(tracemalloc.get_traced_memory()[1] / 1024, 1)
            tracemalloc.stop()
        row["identical_output"] = outputs["p2"] == outputs["p3"]
        row["speedup"] = round(row["p2_seconds"] / row["p3_seconds"], 1)
        print(row, flush=True)
        rows.append(row)
    return rows


def render(report):
    s, disk = report["storage"], report["disk_bytes"]
    lines = ["# Benchmark", "",
             f"Warm cache, median of {REPEATS} runs after one warm-up, each in a fresh process. "
             "RSS increase = peak working set minus the peak after imports; heap = peak traced "
             "Python/NumPy allocations (tracemalloc, one separate run). Pillow's internal decode "
             "buffers are in RSS but not in heap; memory-mapped pages are in RSS but not in heap.", "",
             f"Disk: JPEG folder {disk['jpeg']:,} bytes; .npy cache {disk['npy']:,} bytes.", "",
             "| storage | workload | images | median s | min-max s | RSS increase MiB | heap peak MiB |",
             "|---|---|---|---|---|---|---|"]
    for r in s.values():
        lines.append(f"| {r['method']} | {r['workload']} | {r['images']} | {r['seconds_median']:.3f} | "
                     f"{r['seconds_min']:.3f}-{r['seconds_max']:.3f} | {r['rss_increase_mib_median']} | "
                     f"{r['heap_peak_mib']} |")
    lines += ["", "Huffman bit packer, raw byte stream of one image:", "",
              "| image | P2 s | P3 s | speed-up | P2 heap KiB | P3 heap KiB | identical output |",
              "|---|---|---|---|---|---|---|"]
    for r in report["encoder"]:
        lines.append(f"| {r['path']} | {r['p2_seconds']:.3f} | {r['p3_seconds']:.4f} | {r['speedup']}x | "
                     f"{r['p2_heap_peak_kib']} | {r['p3_heap_peak_kib']} | {r['identical_output']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--worker", nargs=2, metavar=("METHOD", "WORKLOAD"))
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args(argv)
    if args.worker:
        worker(*args.worker, args.trace)
        return
    config, paths, subset = dataset()
    pixel_sha = ensure_cache(config, paths)
    report = {
        "environment": environment_info(), "repeats": REPEATS,
        "decoded_pixels_sha256": pixel_sha,
        "disk_bytes": {"jpeg": sum(e["bytes"] for e in manifest.read(config["manifest"])),
                       "npy": CACHE.stat().st_size},
        "storage": measure_storage(),
        "encoder": measure_encoder(config, subset),
    }
    atomic_write_json(OUT / "bench.json", report)
    atomic_write_text(OUT / "bench.md", render(report))
    print(render(report))


if __name__ == "__main__":
    main()
