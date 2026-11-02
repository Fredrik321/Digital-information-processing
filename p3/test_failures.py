"""Failure handling. Each test runs the real entry point (run.py) on a
temporary copy of the dataset, damages the copy in one specific way, and
checks that the run stops with the right exit code and a message that names
the problem. The real dataset is never modified (checked at the end).

    python test_failures.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import manifest
from common import HERE

DATASET = HERE.parent / "Bird Speciees Dataset"
VICTIM = "BARN OWL/007.jpg"
EVIDENCE = []  # (test, exit code, the message the run printed), shown at the end


class FailureHandling(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="p3-fail-"))
        self.data = self.tmp / "data"
        shutil.copytree(DATASET, self.data)
        shutil.copy(HERE / "manifest.csv", self.tmp / "manifest.csv")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @classmethod
    def tearDownClass(cls):
        # The tests only ever touch copies.
        manifest.verify(DATASET, manifest.read(HERE / "manifest.csv"))
        print("\nexit | test | first error/warning line the run printed")
        for name, code, line in EVIDENCE:
            print(f"{code:>4} | {name} | {line}")
        print("real dataset still matches manifest.csv")

    def config(self, name="fail", **overrides):
        """A small, fast config (6 images, PNG and zlib only) pointing at the copy."""
        cfg = {"run_name": name, "dataset_root": str(self.data),
               "manifest": str(self.tmp / "manifest.csv"), "schema": str(HERE / "schema.json"),
               "out_dir": str(self.tmp / "out"), "log_dir": str(self.tmp / "logs"),
               "seed": 4120, "subset": {"per_class": 1, "include": []},
               "variants": ["png", "zlib-6"], "qa": False, "progress_every": 1, "reference": {}}
        cfg.update(overrides)
        path = self.tmp / f"{name}.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        return path

    def run_pipeline(self, config, *extra):
        # Paths in messages may hold non-ASCII characters; make the child write UTF-8.
        proc = subprocess.run([sys.executable, str(HERE / "run.py"), "--config", str(config), *extra],
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        out = proc.stdout + proc.stderr
        flagged = [l for l in out.splitlines()
                   if " ERROR " in l or " WARNING " in l or "Error:" in l]
        line = (flagged or [l for l in out.splitlines() if "done in" in l] or [""])[0]
        EVIDENCE.append((self._testMethodName, proc.returncode, line.strip()[:170]))
        return proc.returncode, out

    def rebuild_manifest(self):
        """Record the damaged copy in its manifest, as a careless data provider
        would, so the manifest check passes and the schema check is tested."""
        manifest.write(manifest.build(self.data), self.tmp / "manifest.csv", self.tmp / "SHA256SUMS")

    def assertNoResults(self):
        self.assertFalse((self.tmp / "out" / "results.csv").exists())

    def test_0_unmodified_copy_passes(self):
        code, out = self.run_pipeline(self.config())
        self.assertEqual(code, 0, out)

    def test_missing_input_file(self):
        (self.data / VICTIM).unlink()
        code, out = self.run_pipeline(self.config())
        self.assertEqual(code, 2, out)
        self.assertIn(f"missing: {VICTIM}", out)
        self.assertNoResults()

    def test_missing_dataset_root(self):
        shutil.rmtree(self.data)
        code, out = self.run_pipeline(self.config())
        self.assertEqual(code, 2, out)
        self.assertIn("dataset root not found", out)

    def test_missing_config(self):
        code, out = self.run_pipeline(self.tmp / "no_such_config.json")
        self.assertEqual(code, 2, out)
        self.assertIn("config file not found", out)

    def test_digest_mismatch(self):
        path = self.data / VICTIM
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 0x01            # one bit, same file size
        path.write_bytes(bytes(data))
        code, out = self.run_pipeline(self.config())
        self.assertEqual(code, 3, out)
        self.assertIn(f"{VICTIM}: sha256", out)
        self.assertNoResults()

    def test_unlisted_file(self):
        shutil.copy(self.data / VICTIM, self.data / "BARN OWL" / "999.jpg")
        code, out = self.run_pipeline(self.config())
        self.assertEqual(code, 3, out)
        self.assertIn("not in the manifest: BARN OWL/999.jpg", out)

    def test_invalid_shape(self):
        Image.new("RGB", (225, 224), "gray").save(self.data / VICTIM, quality=95)
        self.rebuild_manifest()
        code, out = self.run_pipeline(self.config())
        self.assertEqual(code, 4, out)
        self.assertIn(f"{VICTIM}: size 225x224, expected 224x224", out)
        self.assertNoResults()

    def test_invalid_mode(self):
        Image.new("L", (224, 224), 128).save(self.data / VICTIM, quality=95)
        self.rebuild_manifest()
        code, out = self.run_pipeline(self.config())
        self.assertEqual(code, 4, out)
        self.assertIn(f"{VICTIM}: mode L, expected RGB", out)

    def test_truncated_file(self):
        path = self.data / VICTIM
        path.write_bytes(path.read_bytes()[:5000])
        self.rebuild_manifest()
        code, out = self.run_pipeline(self.config())
        self.assertEqual(code, 4, out)
        self.assertIn("cannot decode", out)

    def test_interrupted_run_resumes(self):
        cfg = self.config()
        code, out = self.run_pipeline(cfg, "--stop-after", "2")
        self.assertEqual(code, 130, out)
        self.assertIn("Rerun the same command to resume", out)
        ckpt = self.tmp / "out" / "checkpoint.jsonl"
        self.assertEqual(len(ckpt.read_text(encoding="utf-8").splitlines()), 3)  # header + 2
        self.assertNoResults()

        # A crash in the middle of writing a checkpoint line leaves a torn line.
        with open(ckpt, "a", encoding="utf-8") as f:
            f.write('{"row": {"path": "BARN OW')
        code, out = self.run_pipeline(cfg)
        self.assertEqual(code, 0, out)
        self.assertIn("dropped 1 incomplete line(s)", out)
        self.assertIn("resuming: 2 of 6 images already done", out)
        self.assertFalse(ckpt.exists())

        # The resumed result is byte-identical to an uninterrupted run.
        clean = self.config("clean", out_dir=str(self.tmp / "out_clean"))
        code, out = self.run_pipeline(clean)
        self.assertEqual(code, 0, out)
        self.assertEqual((self.tmp / "out" / "results.csv").read_bytes(),
                         (self.tmp / "out_clean" / "results.csv").read_bytes())

    def test_resume_refuses_a_changed_run(self):
        code, out = self.run_pipeline(self.config(), "--stop-after", "1")
        self.assertEqual(code, 130, out)
        code, out = self.run_pipeline(self.config(seed=1))
        self.assertEqual(code, 1, out)
        self.assertIn("belongs to a different run", out)
        code, out = self.run_pipeline(self.config(seed=1), "--fresh")
        self.assertEqual(code, 0, out)

    def test_result_differs_from_reference(self):
        # What another pair sees if their Pillow build writes a different PNG.
        cfg = self.config(subset={"per_class": 1, "include": ["AMERICAN GOLDFINCH/001.jpg"]},
                          reference={"AMERICAN GOLDFINCH/001.jpg": {"png": 81983}})
        code, out = self.run_pipeline(cfg)
        self.assertEqual(code, 5, out)
        self.assertIn("AMERICAN GOLDFINCH/001.jpg png: 81979 bytes, reference 81983", out)


if __name__ == "__main__":
    unittest.main()
