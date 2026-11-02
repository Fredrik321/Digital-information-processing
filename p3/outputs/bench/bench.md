# Benchmark

Warm cache, median of 5 runs after one warm-up, each in a fresh process. RSS increase = peak working set minus the peak after imports; heap = peak traced Python/NumPy allocations (tracemalloc, one separate run). Pillow's internal decode buffers are in RSS but not in heap; memory-mapped pages are in RSS but not in heap.

Disk: JPEG folder 15,967,831 bytes; .npy cache 122,078,336 bytes.

| storage | workload | images | median s | min-max s | RSS increase MiB | heap peak MiB |
|---|---|---|---|---|---|---|
| jpeg | all | 811 | 1.369 | 1.321-1.480 | 118.1 | 117.4 |
| jpeg | subset | 14 | 0.035 | 0.035-0.037 | 2.7 | 3.0 |
| npy | all | 811 | 0.761 | 0.754-0.773 | 116.5 | 116.6 |
| npy | subset | 14 | 0.065 | 0.064-0.071 | 117.5 | 118.6 |
| npy_mmap | all | 811 | 0.773 | 0.765-0.809 | 114.6 | 0.1 |
| npy_mmap | subset | 14 | 0.015 | 0.015-0.019 | 3.1 | 2.1 |

Huffman bit packer, raw byte stream of one image:

| image | P2 s | P3 s | speed-up | P2 heap KiB | P3 heap KiB | identical output |
|---|---|---|---|---|---|---|
| AMERICAN GOLDFINCH/001.jpg | 6.575 | 0.0731 | 90.0x | 598.4 | 288.4 | True |
| AMERICAN GOLDFINCH/033.jpg | 6.387 | 0.0388 | 164.6x | 548.6 | 261.5 | True |
| AMERICAN GOLDFINCH/076.jpg | 6.153 | 0.0398 | 154.6x | 598.9 | 288.5 | True |
