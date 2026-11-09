"""Quality-assurance report: missing values, ranges, duplicates, corrupt files.

    python qa.py     # writes outputs/qa/qa_report.json, qa_report.md, near_duplicates.jpg,
                     # near_duplicate_examples.jpg

The report describes the data; it never stops the pipeline. Contract
violations are validate.py's job. Near-duplicate candidates are found with a
64-bit difference hash (dHash); a person decides which candidates are real
duplicates, in qa_review.csv, and the report counts those verdicts.
"""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common import HERE, atomic_write_bytes, atomic_write_json, atomic_write_text
import manifest

# dHash bits; pairs at or below this are listed as candidates. All 35 pairs up
# to 12 were reviewed by eye: every pair <= 6 was a duplicate, pairs at 7-12
# were mixed, and duplicates still appeared at 11, so nothing beyond it is known.
NEAR_DUP_MAX_DISTANCE = 12
REVIEW_FILE = HERE / "qa_review.csv"
# The one-row figure in the report: a copy that looks identical, a re-zoomed copy,
# the farthest re-cropped copy, and a rejected pair at the review limit.
EXAMPLE_PAIRS = [("EMPEROR PENGUIN/125.jpg", "EMPEROR PENGUIN/136.jpg"),
                 ("BARN OWL/024.jpg", "BARN OWL/028.jpg"),
                 ("CARMINE BEE-EATER/004.jpg", "CARMINE BEE-EATER/016.jpg"),
                 ("EMPEROR PENGUIN/071.jpg", "EMPEROR PENGUIN/105.jpg")]

# Standard IJG luminance table (natural order), used to name the JPEG quality.
IJG_LUMA = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55,
            14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62,
            18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
            49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99]


def ijg_quality(luma_table):
    """The IJG quality setting whose luminance table equals this one, or None."""
    for q in range(1, 101):
        scale = 5000 // q if q < 50 else 200 - 2 * q
        if [max(1, min(255, (v * scale + 50) // 100)) for v in IJG_LUMA] == list(luma_table):
            return q
    return None


def dhash(im):
    """64-bit difference hash: is each pixel brighter than its right neighbour,
    on a 9x8 greyscale thumbnail. Robust to re-encoding and small crops."""
    g = np.asarray(im.convert("L").resize((9, 8), Image.LANCZOS), dtype=np.int16)
    return (g[:, 1:] > g[:, :-1]).ravel()


def scan_file(path):
    data = path.read_bytes()
    rec = {"bytes": len(data), "ends_with_eoi": data[-2:] == b"\xff\xd9",
           "verify_ok": True, "decode_ok": True, "error": ""}
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
    except Exception as exc:
        rec.update(verify_ok=False, error=f"verify: {exc}")
    try:
        with Image.open(io.BytesIO(data)) as im:
            rec.update(format=im.format, mode=im.mode, size=list(im.size),
                       has_exif=bool(im.getexif()),
                       quality=ijg_quality(im.quantization[0]) if im.format == "JPEG" else None)
            arr = np.asarray(im.convert("RGB"))
            rec["dhash"] = dhash(im)
    except Exception as exc:
        rec.update(decode_ok=False, error=f"decode: {exc}")
        return rec, None
    return rec, arr


def find_near_duplicates(paths, hashes, max_distance):
    h = np.array(hashes, dtype=np.uint8)
    dist = (h[:, None, :] != h[None, :, :]).sum(-1)
    i, j = np.triu_indices(len(paths), 1)
    d = dist[i, j]
    order = np.argsort(d, kind="stable")
    pairs = [{"a": paths[i[k]], "b": paths[j[k]], "distance": int(d[k]),
              "cross_class": paths[i[k]].split("/")[0] != paths[j[k]].split("/")[0]}
             for k in order if d[k] <= max_distance]
    histogram = {f"<={t}": int((d <= t).sum()) for t in (0, 2, 4, 6, 8, 10, 12)}
    return pairs, histogram


def read_review():
    if not REVIEW_FILE.is_file():
        return {}
    with open(REVIEW_FILE, newline="", encoding="utf-8") as f:
        return {(r["a"], r["b"]): r for r in csv.DictReader(f)}


def duplicate_groups(pairs):
    """Join confirmed duplicate pairs into groups (A~B and B~C gives {A, B, C})."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        parent[find(p["a"])] = find(p["b"])
    groups = defaultdict(list)
    for x in parent:
        groups[find(x)].append(x)
    return sorted(sorted(g) for g in groups.values())


def precision_by_band(pairs):
    bands = {}
    for lo, hi in ((0, 6), (7, 10), (11, NEAR_DUP_MAX_DISTANCE)):
        band = [p for p in pairs if lo <= p["distance"] <= hi]
        dup = sum(p["verdict"] == "duplicate" for p in band)
        bands[f"{lo}-{hi}"] = {"pairs": len(band), "duplicate": dup,
                               "unreviewed": sum(p["verdict"] == "unreviewed" for p in band)}
    return bands


def contact_sheet(root, pairs, out_path, per_row=3, thumb=112, examples=False):
    """All candidates numbered by distance, or (examples=True) a labelled row of examples."""
    if not pairs:
        return
    font = ImageFont.load_default(size=13) if examples else None
    line = 17 if examples else 13
    cell_w, cell_h = 2 * thumb + 12, thumb + 4 + 2 * line
    rows = (len(pairs) + per_row - 1) // per_row
    sheet = Image.new("RGB", (per_row * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    for n, p in enumerate(pairs):
        x, y = (n % per_row) * cell_w, (n // per_row) * cell_h
        for k, rel in enumerate((p["a"], p["b"])):
            with Image.open(root / rel) as im:
                sheet.paste(im.convert("RGB").resize((thumb, thumb)), (x + k * thumb, y))
        short = lambda rel: (rel.split("/")[0].split()[-1][:None if examples else 8]
                             + "/" + rel.split("/")[1][:3])
        head = f"distance {p['distance']}: {p['verdict']}" if examples else f"#{n + 1} d={p['distance']}"
        draw.text((x + 2, y + thumb + 2), head, fill="black", font=font)
        draw.text((x + 2, y + thumb + 2 + line), f"{short(p['a'])} | {short(p['b'])}",
                  fill="black", font=font)
    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=85)
    atomic_write_bytes(out_path, buf.getvalue())


def run_qa(root, entries, out_dir):
    root, out_dir = Path(root), Path(out_dir)
    paths = [e["path"] for e in entries]
    by_class = defaultdict(list)
    recs, pixel_hashes, hashes, decoded = {}, defaultdict(list), [], []
    stats = []
    for rel in paths:
        rec, arr = scan_file(root / rel)
        recs[rel] = rec
        by_class[rel.split("/")[0]].append(rel)
        if arr is None:
            continue
        decoded.append(rel)
        hashes.append(rec.pop("dhash"))
        pixel_hashes[hashlib.sha256(arr.tobytes()).hexdigest()].append(rel)
        flat = arr.reshape(-1, 3)
        stats.append({"path": rel, "min": int(arr.min()), "max": int(arr.max()),
                      "mean": float(arr.mean()), "std": float(arr.std()),
                      "channel_mean": [round(float(m), 2) for m in flat.mean(0)]})

    byte_groups = defaultdict(list)
    for e in entries:
        byte_groups[e["sha256"]].append(e["path"])
    exact_bytes = [g for g in byte_groups.values() if len(g) > 1]
    exact_pixels = [g for g in pixel_hashes.values() if len(g) > 1]
    pairs, histogram = find_near_duplicates(decoded, hashes, NEAR_DUP_MAX_DISTANCE)

    review = read_review()
    for p in pairs:
        r = review.get((p["a"], p["b"]), {})
        p["verdict"] = r.get("verdict", "unreviewed")
        p["reviewed_by"] = r.get("reviewed_by", "")
    confirmed = [p for p in pairs if p["verdict"] == "duplicate"]
    groups = duplicate_groups(confirmed)

    means = np.array([s["mean"] for s in stats])
    stds = np.array([s["std"] for s in stats])
    sizes = np.array([recs[p]["bytes"] for p in paths])
    report = {
        "files": len(paths),
        "per_class": {c: len(v) for c, v in sorted(by_class.items())},
        "missing_values": {
            "zero_byte_files": [p for p in paths if recs[p]["bytes"] == 0],
            "undecodable_files": [p for p in paths if not recs[p]["decode_ok"]],
            "not_rgb": [p for p in decoded if recs[p]["mode"] != "RGB"],
            "constant_images": [s["path"] for s in stats if s["std"] == 0],
            "files_with_exif": sum(recs[p].get("has_exif", False) for p in decoded),
            "note": "Pixels cannot be missing in a decoded JPEG; missing data shows up as "
                    "absent, empty or undecodable files, blank images, or absent metadata.",
        },
        "ranges": {
            "pixel_min": int(min(s["min"] for s in stats)),
            "pixel_max": int(max(s["max"] for s in stats)),
            "images_using_0": sum(s["min"] == 0 for s in stats),
            "images_using_255": sum(s["max"] == 255 for s in stats),
            "image_mean": {"min": round(float(means.min()), 2), "median": round(float(np.median(means)), 2),
                           "max": round(float(means.max()), 2)},
            "image_std": {"min": round(float(stds.min()), 2), "median": round(float(np.median(stds)), 2),
                          "max": round(float(stds.max()), 2)},
            "lowest_contrast": [s["path"] for s in sorted(stats, key=lambda s: s["std"])[:5]],
            "file_bytes": {"min": int(sizes.min()), "median": int(np.median(sizes)),
                           "max": int(sizes.max()), "total": int(sizes.sum())},
        },
        "duplicates": {
            "exact_byte_groups": exact_bytes,
            "exact_pixel_groups": exact_pixels,
            "near_duplicate_method": f"64-bit dHash, Hamming distance <= {NEAR_DUP_MAX_DISTANCE}",
            "near_duplicate_distance_histogram": histogram,
            "near_duplicate_candidates": pairs,
            "confirmed_near_duplicates": len(confirmed),
            "review_by_distance_band": precision_by_band(pairs),
            "duplicate_groups": groups,
            "files_in_duplicate_groups": sum(len(g) for g in groups),
            "redundant_files": sum(len(g) - 1 for g in groups),
            "cross_class_candidates": [p for p in pairs if p["cross_class"]],
            "cross_class_duplicates": [p for p in confirmed if p["cross_class"]],
        },
        "corrupt": {
            "verify_failed": [p for p in paths if not recs[p]["verify_ok"]],
            "decode_failed": [p for p in paths if not recs[p]["decode_ok"]],
            "missing_jpeg_end_marker": [p for p in paths if not recs[p]["ends_with_eoi"]],
            "errors": {p: recs[p]["error"] for p in paths if recs[p]["error"]},
        },
        "encoding": {
            "formats": dict(Counter(recs[p].get("format") for p in decoded)),
            "modes": dict(Counter(recs[p].get("mode") for p in decoded)),
            "sizes": dict(Counter("x".join(map(str, recs[p]["size"])) for p in decoded)),
            "jpeg_quality": dict(Counter(str(recs[p].get("quality")) for p in decoded)),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_dir / "qa_report.json", report)
    atomic_write_text(out_dir / "qa_report.md", render_markdown(report))
    contact_sheet(root, pairs, out_dir / "near_duplicates.jpg")
    examples = [p for key in EXAMPLE_PAIRS for p in pairs if (p["a"], p["b"]) == key]
    contact_sheet(root, examples, out_dir / "near_duplicate_examples.jpg",
                  per_row=max(len(examples), 1), thumb=128, examples=True)
    return report


def render_markdown(r):
    mv, rg, du, co, en = (r["missing_values"], r["ranges"], r["duplicates"],
                          r["corrupt"], r["encoding"])
    lines = [
        "# QA report", "",
        f"Files checked: {r['files']} ({', '.join(f'{c}: {n}' for c, n in r['per_class'].items())})", "",
        "| check | result |", "|---|---|",
        f"| zero-byte files | {len(mv['zero_byte_files'])} |",
        f"| undecodable files | {len(mv['undecodable_files'])} |",
        f"| not RGB before conversion | {len(mv['not_rgb'])} |",
        f"| constant (blank) images | {len(mv['constant_images'])} |",
        f"| files with EXIF metadata | {mv['files_with_exif']} |",
        f"| pixel range | {rg['pixel_min']}-{rg['pixel_max']} |",
        f"| images reaching 0 / 255 | {rg['images_using_0']} / {rg['images_using_255']} |",
        f"| per-image mean (min / median / max) | {rg['image_mean']['min']} / {rg['image_mean']['median']} / {rg['image_mean']['max']} |",
        f"| per-image std (min / median / max) | {rg['image_std']['min']} / {rg['image_std']['median']} / {rg['image_std']['max']} |",
        f"| file size, bytes (min / median / max) | {rg['file_bytes']['min']:,} / {rg['file_bytes']['median']:,} / {rg['file_bytes']['max']:,} |",
        f"| exact byte duplicates (groups) | {len(du['exact_byte_groups'])} |",
        f"| exact pixel duplicates (groups) | {len(du['exact_pixel_groups'])} |",
        f"| near-duplicate candidates ({du['near_duplicate_method']}) | {len(du['near_duplicate_candidates'])} |",
        f"| near-duplicate pairs confirmed by review | {du['confirmed_near_duplicates']} |",
        f"| duplicate groups / files in them / redundant copies | {len(du['duplicate_groups'])} / {du['files_in_duplicate_groups']} / {du['redundant_files']} |",
        f"| cross-class candidates / confirmed | {len(du['cross_class_candidates'])} / {len(du['cross_class_duplicates'])} |",
        f"| Pillow verify() failures | {len(co['verify_failed'])} |",
        f"| full-decode failures | {len(co['decode_failed'])} |",
        f"| missing JPEG end marker (truncation) | {len(co['missing_jpeg_end_marker'])} |",
        f"| formats / modes / sizes | {en['formats']} / {en['modes']} / {en['sizes']} |",
        f"| JPEG quality (IJG table match) | {en['jpeg_quality']} |",
        "", "## Near-duplicate candidates", "",
        f"dHash distance histogram over all pairs: {du['near_duplicate_distance_histogram']}", "",
        "| distance band | pairs | duplicates | unreviewed |", "|---|---|---|---|",
    ]
    for band, b in du["review_by_distance_band"].items():
        lines.append(f"| {band} | {b['pairs']} | {b['duplicate']} | {b['unreviewed']} |")
    lines += ["", "| # | a | b | distance | verdict | reviewed by |", "|---|---|---|---|---|---|"]
    for n, p in enumerate(du["near_duplicate_candidates"], 1):
        lines.append(f"| {n} | {p['a']} | {p['b']} | {p['distance']} | {p['verdict']} | {p['reviewed_by']} |")
    lines += ["", "Duplicate groups:", ""]
    lines += [f"- {', '.join(g)}" for g in du["duplicate_groups"]]
    lines += ["", f"Lowest-contrast images: {', '.join(rg['lowest_contrast'])}", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(manifest.DEFAULT_ROOT))
    parser.add_argument("--manifest", default=str(HERE / "manifest.csv"))
    parser.add_argument("--out", default=str(HERE / "outputs" / "qa"))
    args = parser.parse_args(argv)
    report = run_qa(args.root, manifest.read(args.manifest), args.out)
    print(json.dumps({k: report["duplicates"][k] for k in
                      ("near_duplicate_distance_histogram", "confirmed_near_duplicates")}))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
