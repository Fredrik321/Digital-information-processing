"""Build and verify the dataset manifest: relative path, byte size, SHA-256.

    python manifest.py build     # write manifest.csv and SHA256SUMS
    python manifest.py verify    # check the dataset against manifest.csv

Paths are relative to the dataset root and use "/" separators, so the
manifest is the same on every platform. SHA256SUMS has the standard
`sha256sum` format and can be checked without any of our code:

    cd "Bird Speciees Dataset" && sha256sum -c ../p3/SHA256SUMS
"""
import argparse
import csv
import io
import sys
from pathlib import Path

from common import (HERE, IntegrityError, MissingInputError, PipelineError,
                    atomic_write_text, sha256_file)

FIELDS = ["path", "bytes", "sha256"]
DEFAULT_ROOT = HERE.parent / "Bird Speciees Dataset"
SHOW = 10  # how many offending paths an error message lists


def list_files(root):
    """Every file under root (hidden ones included), as sorted relative POSIX paths."""
    return sorted(p.relative_to(root).as_posix() for p in Path(root).rglob("*") if p.is_file())


def build(root):
    root = Path(root)
    if not root.is_dir():
        raise MissingInputError(f"dataset root not found: {root}")
    return [{"path": rel, "bytes": (root / rel).stat().st_size,
             "sha256": sha256_file(root / rel)} for rel in list_files(root)]


def write(entries, csv_path, sums_path):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(entries)
    atomic_write_text(csv_path, buf.getvalue())
    atomic_write_text(sums_path, "".join(f"{e['sha256']}  {e['path']}\n" for e in entries))


def read(csv_path):
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise MissingInputError(f"manifest not found: {csv_path}")
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise IntegrityError(f"manifest columns are {reader.fieldnames}, expected {FIELDS}")
        entries = [{"path": r["path"], "bytes": int(r["bytes"]), "sha256": r["sha256"]}
                   for r in reader]
    if not entries:
        raise IntegrityError(f"manifest is empty: {csv_path}")
    return entries


def _listing(paths):
    more = f" (+{len(paths) - SHOW} more)" if len(paths) > SHOW else ""
    return ", ".join(paths[:SHOW]) + more


def verify(root, entries):
    """Raise MissingInputError if a listed file is absent, IntegrityError if a
    file is unlisted or its size or SHA-256 differs. Returns a summary."""
    root = Path(root)
    if not root.is_dir():
        raise MissingInputError(f"dataset root not found: {root}")
    on_disk = set(list_files(root))
    listed = [e["path"] for e in entries]

    missing = [p for p in listed if p not in on_disk]
    if missing:
        raise MissingInputError(f"{len(missing)} file(s) listed in the manifest are "
                                f"missing: {_listing(missing)}")
    unlisted = sorted(on_disk - set(listed))
    if unlisted:
        raise IntegrityError(f"{len(unlisted)} file(s) are not in the manifest: "
                             f"{_listing(unlisted)}")

    problems = []
    for e in entries:
        path = root / e["path"]
        size = path.stat().st_size
        if size != e["bytes"]:
            problems.append(f"{e['path']}: size {size} bytes, manifest says {e['bytes']}")
            continue
        actual = sha256_file(path)
        if actual != e["sha256"]:
            problems.append(f"{e['path']}: sha256 {actual[:16]}..., "
                            f"manifest says {e['sha256'][:16]}...")
    if problems:
        raise IntegrityError(f"{len(problems)} file(s) do not match the manifest: "
                             f"{_listing(problems)}")
    return {"files": len(entries), "bytes": sum(e["bytes"] for e in entries)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["build", "verify"])
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--manifest", default=str(HERE / "manifest.csv"))
    parser.add_argument("--sums", default=str(HERE / "SHA256SUMS"))
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            entries = build(args.root)
            write(entries, args.manifest, args.sums)
            print(f"wrote {len(entries)} entries to {args.manifest} and {args.sums}")
        else:
            summary = verify(args.root, read(args.manifest))
            print(f"OK: {summary['files']} files, {summary['bytes']:,} bytes match the manifest")
    except PipelineError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main())
