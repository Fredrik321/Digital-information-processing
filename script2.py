import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from PIL import Image

ROOT = Path("Bird Speciees Dataset")
classes = sorted(p for p in ROOT.iterdir() if p.is_dir())

# --- Grid: one sample per class ---
n = len(classes)
cols = 6
rows = (n + cols - 1) // cols
fig, axes = plt.subplots(rows, cols, figsize=(cols*2, rows*2.2))
axes = axes.ravel()

for ax, cls in zip(axes, classes):
    imgs = sorted((cls).glob("*"))
    arr = np.asarray(Image.open(imgs[0]).convert("RGB"))
    ax.imshow(arr)
    ax.set_title(f"{cls.name}\n(n={len(imgs)})", fontsize=8)
    ax.set_xlabel("x (pixels)", fontsize=7)
    ax.set_ylabel("y (pixels)", fontsize=7)
    ax.tick_params(labelsize=6)

for ax in axes[n:]:
    ax.axis("off")

plt.suptitle("Spatial view: one sample per bird class", fontsize=11)
plt.tight_layout()
plt.savefig("spatial_grid.png", dpi=150, bbox_inches="tight")

# --- Single image with colour bar ---
sample = np.asarray(Image.open(sorted(classes[0].glob('*'))[0]).convert("RGB"))
fig, ax = plt.subplots(figsize=(5, 5))
im = ax.imshow(sample)
ax.set_xlabel("x (pixels)")
ax.set_ylabel("y (pixels)")
cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
cbar.set_label("Intensity (0–255, uint8)")
ax.set_title(f"Spatial view: representative image ({classes[0].name})")
plt.tight_layout()
plt.savefig("spatial_single.png", dpi=150)