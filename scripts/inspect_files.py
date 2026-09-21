import os
import statistics
from pathlib import Path
from collections import defaultdict

ROOT = Path("Bird Speciees Dataset")   # <-- change this

EXTS = {".jpg", ".jpeg", ".png"}

def human(n_bytes: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024
    return f"{n_bytes:.1f} TiB"

# ---------- Collect per-file stats ----------
records = []
for p in ROOT.rglob("*"):
    if p.suffix.lower() not in EXTS:
        continue
    st = os.stat(p)
    records.append({
        "path": p,
        "class": p.parent.name,
        "size_bytes": st.st_size,
        "mtime": st.st_mtime,
        "ctime": st.st_ctime,
        "inode": st.st_ino,
        "mode": st.st_mode,
    })

print(f"Files found : {len(records)}")

# ---------- Global size stats ----------
sizes = [r["size_bytes"] for r in records]
total = sum(sizes)

print(f"Total on disk     : {human(total)}  ({total:,} bytes)")
print(f"Min file size     : {human(min(sizes))}")
print(f"Max file size     : {human(max(sizes))}")
print(f"Mean file size    : {human(int(statistics.mean(sizes)))}")
print(f"Median file size  : {human(int(statistics.median(sizes)))}")
print(f"Std dev           : {human(int(statistics.pstdev(sizes)))}")

# ---------- Per-class size stats ----------
by_class = defaultdict(list)
for r in records:
    by_class[r["class"]].append(r["size_bytes"])

print("\nPer-class summary:")
print(f"{'class':25s} {'n':>5s} {'total':>12s} {'mean':>12s} {'min':>10s} {'max':>10s}")
for cls in sorted(by_class):
    s = by_class[cls]
    print(f"{cls:25s} {len(s):5d} {human(sum(s)):>12s} "
          f"{human(int(statistics.mean(s))):>12s} "
          f"{human(min(s)):>10s} {human(max(s)):>10s}")

# ---------- Unusual files ----------
# Very small files often indicate truncated or corrupt images.
SMALL = 5_000  # bytes; adjust to taste
small = [r for r in records if r["size_bytes"] < SMALL]
if small:
    print(f"\nFiles smaller than {human(SMALL)} (possible corruption):")
    for r in small:
        print(f"  {r['path']}  ->  {human(r['size_bytes'])}")

# Very large files may indicate high-quality JPEGs or PNGs saved as raw.
LARGE = 2_000_000
large = [r for r in records if r["size_bytes"] > LARGE]
if large:
    print(f"\nFiles larger than {human(LARGE)}:")
    for r in large:
        print(f"  {r['path']}  ->  {human(r['size_bytes'])}")

# ---------- Duplicate detection via inode ----------
# Same inode = same file hard-linked or copied into two class folders.
inodes = defaultdict(list)
for r in records:
    inodes[r["inode"]].append(r["path"])

dupes = {k: v for k, v in inodes.items() if len(v) > 1}
if dupes:
    print(f"\nDuplicate files (same inode, {len(dupes)} groups):")
    for k, v in dupes.items():
        print(f"  inode {k}:")
        for path in v:
            print(f"    {path}")
else:
    print("\nNo duplicate inodes found.")

# ---------- Timestamp range ----------
import datetime as dt
mtimes = sorted(r["mtime"] for r in records)
print("\nModification time range:")
print(f"  earliest: {dt.datetime.fromtimestamp(mtimes[0])}")
print(f"  latest  : {dt.datetime.fromtimestamp(mtimes[-1])}")

# ---------- Summary for the P1 report ----------
print("\n" + "=" * 60)
print("P1 FILE-LEVEL FACTS")
print("=" * 60)
print(f"Images               : {len(records)}")
print(f"Total size on disk   : {human(total)}")
print(f"Mean file size       : {human(int(statistics.mean(sizes)))}")
print(f"Compressed byte/pixel: "
      f"{total / (len(records)*224*224*3):.3f}  "
      f"(raw uint8 RGB = 1.000)")
print(f"Compression ratio    : "
      f"{(len(records)*224*224*3) / total:.1f}x")