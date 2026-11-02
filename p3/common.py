"""Shared helpers: error types and exit codes, config loading, hashing,
atomic writes, environment and memory information."""
import hashlib
import json
import os
import platform
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent


# Every expected failure maps to its own exit code, so a caller (or the
# failure tests) can tell them apart without parsing messages.
class PipelineError(Exception):
    exit_code = 1


class MissingInputError(PipelineError):
    exit_code = 2


class IntegrityError(PipelineError):
    exit_code = 3


class SchemaError(PipelineError):
    exit_code = 4


class ReproducibilityError(PipelineError):
    exit_code = 5


EXIT_INTERRUPTED = 130


def sha256_file(path, chunk_size=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path, data):
    """Write to a temporary file next to `path`, then rename it into place.
    A crash leaves either the old file or the new one, never half of one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_text(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path, obj):
    atomic_write_text(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def load_config(path):
    """Read a JSON config. Relative paths in it are resolved against the
    config file's own folder, so the pipeline runs from any working directory."""
    path = Path(path).resolve()
    if not path.is_file():
        raise MissingInputError(f"config file not found: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    for key in ("dataset_root", "manifest", "schema", "out_dir", "log_dir"):
        config[key] = str((path.parent / config[key]).resolve())
    if isinstance(config.get("qa"), str):  # "qa" is a folder, or false to skip QA
        config["qa"] = str((path.parent / config["qa"]).resolve())
    config["_path"] = str(path)
    config["_sha256"] = sha256_file(path)
    return config


def environment_info():
    import numpy
    import PIL
    from PIL import features
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": numpy.__version__,
        "pillow": PIL.__version__,
        "pillow_zlib": features.version("zlib"),
        "pillow_libjpeg_turbo": features.version("libjpeg_turbo"),
        "python_zlib": zlib.ZLIB_RUNTIME_VERSION,
    }


def peak_rss_bytes():
    """Peak resident memory of this process so far (Windows: peak working set)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        get_info = kernel32.K32GetProcessMemoryInfo
        get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters),
                             wintypes.DWORD]
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not get_info(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return -1
        return counters.PeakWorkingSetSize
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024
