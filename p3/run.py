"""Single entry point for the P3 pipeline.

    python run.py                             # small test pipeline (config.json)
    python run.py --config config_full.json   # every image in the dataset
    python run.py --fresh                     # discard an unfinished run's checkpoint
    python run.py --stop-after 3              # simulate an interruption (failure tests)

Steps: verify the manifest -> check the schema -> QA report -> codec
pipeline on a seeded subset -> results, summary and a short log.

Exit codes: 0 ok, 1 unexpected error, 2 missing input, 3 input does not
match the manifest, 4 schema violation, 5 result differs from the
reference, 130 interrupted (rerun the same command to resume).
"""
import argparse
import csv
import io
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from common import (EXIT_INTERRUPTED, HERE, PipelineError, ReproducibilityError,
                    atomic_write_json, atomic_write_text, environment_info, load_config,
                    peak_rss_bytes, sha256_bytes, sha256_file)
import manifest
import pipeline
import qa
import validate

log = logging.getLogger("p3")


def setup_logging(log_dir, run_name):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    path = Path(log_dir) / f"{run_name}_{datetime.now():%Y%m%d-%H%M%S}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    for handler in (logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    return path


def check_requirements(env):
    """Warn (do not fail) when installed versions differ from requirements.txt."""
    req = HERE / "requirements.txt"
    if not req.is_file():
        return
    installed = {"numpy": env["numpy"], "pillow": env["pillow"]}
    for line in req.read_text(encoding="utf-8").splitlines():
        name, _, version = line.strip().partition("==")
        if name.lower() in installed and installed[name.lower()] != version:
            log.warning("%s %s installed, requirements.txt pins %s - PNG sizes may differ",
                        name, installed[name.lower()], version)


def to_csv(rows, fields):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def read_checkpoint(path, run_key):
    """Completed images from an interrupted run. A line cut off by a crash is
    dropped (that image is simply redone); a checkpoint from a different
    config, dataset or code version is refused."""
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        header = json.loads(lines[0])
    except (IndexError, json.JSONDecodeError):
        header = {}
    if header.get("run_key") != run_key:
        raise PipelineError(f"{path.name} belongs to a different run (config, data or code "
                            "changed); rerun with --fresh to discard it")
    done, dropped = {}, 0
    for line in lines[1:]:
        try:
            entry = json.loads(line)
            done[entry["row"]["path"]] = (entry["row"], entry["timing"])
        except (json.JSONDecodeError, KeyError, TypeError):
            dropped += 1
    if dropped:
        log.warning("checkpoint: dropped %d incomplete line(s)", dropped)
    # Rewrite without the damaged lines so new lines are not appended to a torn one.
    atomic_write_text(path, "".join(json.dumps(x) + "\n" for x in
                                    [header] + [{"row": r, "timing": t} for r, t in done.values()]))
    return done


def check_reference(rows, reference):
    by_path = {r["path"]: r for r in rows}
    mismatches = []
    for rel, expected in reference.items():
        if rel not in by_path:
            log.warning("reference image %s is not in this subset; not checked", rel)
            continue
        for variant, size in expected.items():
            got = by_path[rel].get(variant)
            if got is None:
                continue
            if got != size:
                mismatches.append(f"{rel} {variant}: {got} bytes, reference {size}")
    return mismatches


def run(config, args):
    started = time.perf_counter()
    root, out_dir = Path(config["dataset_root"]), Path(config["out_dir"])
    env = environment_info()
    log.info("run %s started %s", config["run_name"], datetime.now().isoformat(timespec="seconds"))
    log.info("config %s (sha256 %s), seed %s", Path(config["_path"]).name,
             config["_sha256"][:16], config["seed"])
    log.info("env python %s | numpy %s | pillow %s (zlib %s, libjpeg-turbo %s) | %s",
             env["python"], env["numpy"], env["pillow"], env["pillow_zlib"],
             env["pillow_libjpeg_turbo"], env["platform"])
    check_requirements(env)

    # 1. Inputs are exactly the files the manifest lists.
    entries = manifest.read(config["manifest"])
    manifest_sha = sha256_file(config["manifest"])
    m = manifest.verify(root, entries)
    log.info("manifest OK: %d files, %s bytes (manifest sha256 %s)",
             m["files"], f"{m['bytes']:,}", manifest_sha[:16])

    # 2. Every file meets the contract; the digest pins the decoder's output.
    schema = validate.load_schema(config["schema"])
    paths = [e["path"] for e in entries]
    pixel_sha = validate.validate_all(root, paths, schema)
    log.info("schema OK: %d files are %s %s %s; decoded pixels sha256 %s", len(paths),
             schema["file"]["format"], schema["file"]["mode"], tuple(schema["array"]["shape"]),
             pixel_sha[:16])

    # 3. Descriptive QA report (never stops the run).
    if config.get("qa"):
        r = qa.run_qa(root, entries, config["qa"])
        d = r["duplicates"]
        log.info("qa: %d exact duplicate groups, %d near-duplicate pairs confirmed in %d groups "
                 "(%d redundant files), %d corrupt", len(d["exact_byte_groups"]),
                 d["confirmed_near_duplicates"], len(d["duplicate_groups"]), d["redundant_files"],
                 len(r["corrupt"]["decode_failed"]))

    # 4. Codec pipeline on a seeded, stratified subset, with a checkpoint.
    variants = config["variants"]
    unknown = [v for v in variants if v not in pipeline.VARIANTS]
    if unknown:
        raise PipelineError(f"unknown variant(s) in config: {unknown}")
    subset = pipeline.select_subset(paths, config["subset"]["per_class"], config["seed"],
                                    config["subset"].get("include", []))
    code_sha = sha256_bytes(b"".join((HERE / f).read_bytes() for f in ("codec.py", "pipeline.py")))
    run_key = sha256_bytes(json.dumps({"subset": subset, "variants": variants,
                                       "manifest": manifest_sha, "code": code_sha}).encode())
    log.info("subset: %d images (per_class=%s, seed %s), variants %s",
             len(subset), config["subset"]["per_class"], config["seed"], ", ".join(variants))

    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = out_dir / "checkpoint.jsonl"
    done = {}
    if ckpt.exists() and args.fresh:
        ckpt.unlink()
        log.info("discarded existing checkpoint (--fresh)")
    if ckpt.exists():
        done = read_checkpoint(ckpt, run_key)
        log.info("resuming: %d of %d images already done", len(done), len(subset))
    else:
        atomic_write_text(ckpt, json.dumps({"run_key": run_key}) + "\n")

    every = config.get("progress_every", 10)
    processed = 0
    with open(ckpt, "a", encoding="utf-8") as f:
        for rel in subset:
            if rel in done:
                continue
            if args.stop_after is not None and processed >= args.stop_after:
                raise KeyboardInterrupt(f"simulated by --stop-after {args.stop_after}")
            arr = validate.load_image(root / rel, schema, rel)
            row, timing = pipeline.evaluate_image(rel, arr, variants)
            f.write(json.dumps({"row": row, "timing": timing}) + "\n")
            f.flush()
            os.fsync(f.fileno())
            done[rel] = (row, timing)
            processed += 1
            if len(done) % every == 0 or len(done) == len(subset):
                log.info("progress %d/%d (%.0f s)", len(done), len(subset),
                         time.perf_counter() - started)

    # 5. Outputs. results.csv and summary.json hold only deterministic values,
    #    so their digests can be compared between machines.
    rows = [done[rel][0] for rel in subset]
    timings = [done[rel][1] for rel in subset]
    fields = ["path", "class", "raw_bytes", "header_bytes", *variants, "zlib6_unframed", "best"]
    results_csv = to_csv(rows, fields)
    summary = pipeline.summarise(rows, variants)
    summary_text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    atomic_write_text(out_dir / "results.csv", results_csv)
    atomic_write_text(out_dir / "summary.json", summary_text)
    atomic_write_text(out_dir / "timings.csv", to_csv(timings, list(timings[0])))
    mismatches = check_reference(rows, config.get("reference", {}))
    elapsed = time.perf_counter() - started
    atomic_write_json(out_dir / "run.json", {
        "config": {k: v for k, v in config.items() if not k.startswith("_")},
        "config_sha256": config["_sha256"], "environment": env,
        "manifest_sha256": manifest_sha, "decoded_pixels_sha256": pixel_sha,
        "code_sha256": code_sha, "subset": subset,
        "results_csv_sha256": sha256_bytes(results_csv.encode()),
        "summary_json_sha256": sha256_bytes(summary_text.encode()),
        "reference_mismatches": mismatches,
        "seconds": round(elapsed, 1), "peak_rss_bytes": peak_rss_bytes(),
    })
    ckpt.unlink()

    for v, s in summary["variants"].items():
        log.info("%-20s total %11s bytes  ratio %.3f  per-image median %.3f [%.3f-%.3f]",
                 v, f"{s['total_bytes']:,}", s["aggregate_ratio"], s["per_image_ratio"]["median"],
                 s["per_image_ratio"]["min"], s["per_image_ratio"]["max"])
    log.info("results.csv sha256 %s, summary.json sha256 %s",
             sha256_bytes(results_csv.encode())[:16], sha256_bytes(summary_text.encode())[:16])
    log.info("outputs in %s", os.path.relpath(out_dir, Path(config["_path"]).parent))
    if mismatches:
        raise ReproducibilityError(f"{len(mismatches)} size(s) differ from the reference: "
                                   + "; ".join(mismatches))
    if config.get("reference"):
        log.info("reference check OK: P2's reported sizes reproduced exactly")
    log.info("done in %.1f s, peak memory %.0f MiB", elapsed, peak_rss_bytes() / 2**20)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=str(HERE / "config.json"))
    parser.add_argument("--fresh", action="store_true", help="discard an unfinished run's checkpoint")
    parser.add_argument("--stop-after", type=int, default=None, metavar="N",
                        help="interrupt after N images (for the failure tests)")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except PipelineError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return exc.exit_code
    log_path = setup_logging(config["log_dir"], config["run_name"])
    try:
        run(config, args)
    except PipelineError as exc:
        log.error("%s: %s", type(exc).__name__, exc)
        log.error("stopped with exit code %d (log: %s)", exc.exit_code, log_path)
        return exc.exit_code
    except KeyboardInterrupt as exc:
        reason = f" ({exc})" if str(exc) else ""
        log.warning("interrupted%s; finished images are kept in the checkpoint. "
                    "Rerun the same command to resume.", reason)
        return EXIT_INTERRUPTED
    except Exception:
        log.exception("unexpected error")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
