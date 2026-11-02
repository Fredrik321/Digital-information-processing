"""The test pipeline: run every codec variant on each selected image, check
the round trip is exact, and summarise the sizes."""
import time
import zlib

import numpy as np

from codec import compress, container_sizes, decompress, describe_compressed, describe_predictor

# Every variant is forced, and its label is checked against the container
# header, so a number can never be attributed to the wrong codec.
VARIANTS = {
    "huffman": {"image_codec": "huffman", "predictor": "none"},
    "huffman+horizontal": {"image_codec": "huffman", "predictor": "horizontal"},
    "huffman+vertical": {"image_codec": "huffman", "predictor": "vertical"},
    "png": {"image_codec": "png"},
    "zlib-6": {"image_codec": "zlib", "zlib_level": 6},
}
EXPECTED_HEADER = {"huffman": ("huffman", "none"), "huffman+horizontal": ("huffman", "horizontal"),
                   "huffman+vertical": ("huffman", "vertical"), "png": ("png", "none"),
                   "zlib-6": ("zlib", "none")}


def select_subset(paths, per_class, seed, include=()):
    """Deterministic, stratified choice: `per_class` files from each class,
    drawn with a seeded generator, plus any explicitly included files.
    per_class="all" selects every file."""
    if per_class == "all":
        return list(paths)
    rng = np.random.default_rng(seed)
    by_class = {}
    for p in paths:
        by_class.setdefault(p.split("/")[0], []).append(p)
    chosen = set(include)
    for cls in sorted(by_class):
        files = by_class[cls]
        picks = rng.choice(len(files), size=min(per_class, len(files)), replace=False)
        chosen.update(files[i] for i in picks)
    return sorted(chosen)


def evaluate_image(rel, arr, variants):
    """Returns (row, timing). `row` holds only deterministic values so that
    results.csv is byte-identical across runs; times go to `timing`."""
    raw = arr.tobytes()
    row = {"path": rel, "class": rel.split("/")[0], "raw_bytes": len(raw),
           "header_bytes": None, "zlib6_unframed": len(zlib.compress(raw, 6))}
    timing = {"path": rel}
    for name in variants:
        t0 = time.perf_counter()
        comp = compress(arr, VARIANTS[name])
        t1 = time.perf_counter()
        back = decompress(comp)
        t2 = time.perf_counter()
        if not (back.shape == arr.shape and back.dtype == arr.dtype and np.array_equal(back, arr)):
            raise AssertionError(f"{rel}: {name} round trip is not exact")
        if (describe_compressed(comp), describe_predictor(comp)) != EXPECTED_HEADER[name]:
            raise AssertionError(f"{rel}: {name} container header says "
                                 f"{describe_compressed(comp)}+{describe_predictor(comp)}")
        header, _payload = container_sizes(comp)
        row["header_bytes"] = header
        row[name] = len(comp)
        timing[f"{name}_encode_s"] = round(t1 - t0, 4)
        timing[f"{name}_decode_s"] = round(t2 - t1, 4)
    row["best"] = min(variants, key=lambda v: (row[v], v))
    return row, timing


def _spread(values):
    q1, med, q3 = np.percentile(values, [25, 50, 75])
    return {"min": round(float(np.min(values)), 4), "q1": round(float(q1), 4),
            "median": round(float(med), 4), "q3": round(float(q3), 4),
            "max": round(float(np.max(values)), 4)}


def summarise(rows, variants):
    raw_total = sum(r["raw_bytes"] for r in rows)
    out = {"images": len(rows), "raw_bytes": raw_total,
           "header_bytes_per_container": rows[0]["header_bytes"] if rows else None,
           "variants": {}, "per_class": {}}
    for v in variants + ["zlib6_unframed"]:
        total = sum(r[v] for r in rows)
        ratios = np.array([r["raw_bytes"] / r[v] for r in rows])
        worst = min(rows, key=lambda r: (r["raw_bytes"] / r[v], r["path"]))
        best = max(rows, key=lambda r: (r["raw_bytes"] / r[v], r["path"]))
        out["variants"][v] = {
            "total_bytes": total,
            "aggregate_ratio": round(raw_total / total, 4),
            "bits_per_byte": round(8 * total / raw_total, 4),
            "per_image_ratio": _spread(ratios),
            "worst_image": worst["path"], "best_image": best["path"],
            "smallest_on": sum(r["best"] == v for r in rows),
        }
    for cls in sorted({r["class"] for r in rows}):
        sub = [r for r in rows if r["class"] == cls]
        raw = sum(r["raw_bytes"] for r in sub)
        out["per_class"][cls] = {"images": len(sub), **{
            v: round(raw / sum(r[v] for r in sub), 4) for v in variants + ["zlib6_unframed"]}}
    return out
