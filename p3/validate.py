"""Check the dataset against the contract in schema.json.

Unlike the P1/P2 loader this does not call .convert("RGB"): a greyscale or
CMYK file is reported as a violation instead of being silently converted.
"""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from common import MissingInputError, SchemaError

SHOW = 10


def load_schema(path):
    path = Path(path)
    if not path.is_file():
        raise MissingInputError(f"schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_layout(paths, schema):
    """Class folders, per-class counts and file names, from the path list alone."""
    pattern = re.compile(schema["layout"]["file_name_regex"])
    problems = []
    counts = Counter()
    for rel in paths:
        parts = rel.split("/")
        if len(parts) != 2:
            problems.append(f"{rel}: not inside exactly one class folder")
            continue
        cls, name = parts
        if cls not in schema["classes"]:
            problems.append(f"{rel}: unknown class {cls!r}")
        if not pattern.match(name):
            problems.append(f"{rel}: file name does not match {pattern.pattern}")
        counts[cls] += 1
    for cls, expected in schema["classes"].items():
        if counts[cls] != expected:
            problems.append(f"{cls}: {counts[cls]} files, schema expects {expected}")
    if problems:
        raise SchemaError(f"{len(problems)} layout problem(s): " + "; ".join(problems[:SHOW]))
    return dict(counts)


def load_image(path, schema, name=None):
    """Open one file, check it against the contract and return its array.
    `name` (the dataset-relative path) is what error messages show."""
    f, a = schema["file"], schema["array"]
    name = name or str(path)
    try:
        with Image.open(path) as im:
            fmt, mode, size = im.format, im.mode, im.size
            if fmt != f["format"]:
                raise SchemaError(f"{name}: format {fmt}, expected {f['format']}")
            if mode != f["mode"]:
                raise SchemaError(f"{name}: mode {mode}, expected {f['mode']}")
            if size != (f["width"], f["height"]):
                raise SchemaError(f"{name}: size {size[0]}x{size[1]}, "
                                  f"expected {f['width']}x{f['height']}")
            arr = np.asarray(im)
    except SchemaError:
        raise
    except FileNotFoundError:
        raise MissingInputError(f"{name}: file not found")
    except Exception as exc:  # Pillow raises several types for damaged files
        raise SchemaError(f"{name}: cannot decode ({type(exc).__name__}: {exc})")
    if arr.shape != tuple(a["shape"]) or arr.dtype != np.dtype(a["dtype"]):
        raise SchemaError(f"{name}: array {arr.shape} {arr.dtype}, "
                          f"expected {tuple(a['shape'])} {a['dtype']}")
    return arr


def validate_all(root, paths, schema):
    """Decode every file and check it. Collects all violations before raising.
    Returns the SHA-256 of the decoded pixels of all files, in manifest
    order, so two machines can confirm their JPEG decoders agree."""
    check_layout(paths, schema)
    digest = hashlib.sha256()
    problems = []
    for rel in paths:
        try:
            digest.update(load_image(Path(root) / rel, schema, rel).tobytes())
        except SchemaError as exc:
            problems.append(str(exc))
    if problems:
        raise SchemaError(f"{len(problems)} file(s) break the schema: "
                          + "; ".join(problems[:SHOW]))
    return digest.hexdigest()
