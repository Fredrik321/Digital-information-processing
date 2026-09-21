from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path("Bird Speciees Dataset")

shapes = []
dtypes = set()
for p in ROOT.rglob("*"):
    if p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        with Image.open(p) as im:
            arr = np.asarray(im.convert("RGB"))
        shapes.append(arr.shape)
        dtypes.add(arr.dtype)

shapes = np.array(shapes)
print("N images:", len(shapes))
print("dtype(s):", dtypes)
print("H min/mean/max:", shapes[:,0].min(), shapes[:,0].mean(), shapes[:,0].max())
print("W min/mean/max:", shapes[:,1].min(), shapes[:,1].mean(), shapes[:,1].max())
print("channels unique:", np.unique(shapes[:,2]))
print("all same size?:", (shapes[:,0].std() == 0) and (shapes[:,1].std() == 0))