# P3 · Bird Speciees Dataset as a product

The dataset (`../Bird Speciees Dataset`, 811 JPEG files) and the P2 codec are packaged here so that another pair can verify the inputs, reproduce the result, and see where it stops being reliable. The report, with the datasheet, is [p3.md](p3.md).

## Quick start

```bash
cd p3
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # Windows; on Linux/macOS: .venv/bin/python
.venv/Scripts/python run.py
```

The run should end with `reference check OK` and exit code 0. Compare these digests with the ones in [p3.md](p3.md):

- `results.csv sha256` and `summary.json sha256` from the log;
- `decoded pixels sha256`, which shows that your JPEG decoder produced the same pixels.

## Verify the inputs without our code

```bash
cd "Bird Speciees Dataset"
sha256sum -c ../p3/SHA256SUMS
```

On Windows without `sha256sum`, use `Get-FileHash -Algorithm SHA256 <file>` on any row of `manifest.csv`. The manifest itself has SHA-256 `6af9010bab12a83348f0ef68bdf416de97bb5564bd7cd2e300d554f3b83448c3`.

## Files

| file | what it is |
|---|---|
| `run.py` | the single entry point: manifest → schema → QA → codec pipeline → outputs and log |
| `config.json` | small test pipeline: 14 images (2 per class with seed 4120, plus P2's two reference images) |
| `config_full.json` | the same pipeline on all 811 images |
| `manifest.csv`, `SHA256SUMS` | relative path, byte size and SHA-256 for every dataset file; `manifest.py build/verify` |
| `schema.json`, `validate.py` | the shape and type contract, and its checker |
| `qa.py`, `qa_review.csv` | QA report; manual verdicts for near-duplicate candidates |
| `codec.py`, `pipeline.py` | the P2 codec (plus zlib in the same container) and the per-image evaluation |
| `bench.py` | timing and memory: JPEG folder vs `.npy` vs memory-mapped `.npy`; P2 vs P3 Huffman encoder |
| `test_failures.py` | failure handling: missing input, digest mismatch, invalid shape, interrupted run, and more |
| `make_pdf.py` | renders `p3.md` to `Deliverable/p3.pdf` (needs `markdown` and Chrome or Edge; not part of the pipeline) |
| `outputs/` | committed evidence: `qa/`, `test/`, `full/`, `bench/`, `failure_tests.txt` |
| `logs/` | the logs of the runs behind `outputs/` |

## Exit codes

| code | meaning |
|---|---|
| 0 | finished; outputs written |
| 1 | unexpected error, or a checkpoint from a different run (use `--fresh`) |
| 2 | missing input: config, dataset folder or a listed file |
| 3 | inputs do not match the manifest: SHA-256, size, or an unlisted file |
| 4 | schema violation: wrong format, mode or size, or undecodable |
| 5 | a result differs from the P2 reference (usually a different Pillow build) |
| 130 | interrupted; rerun the same command to resume from the checkpoint |
