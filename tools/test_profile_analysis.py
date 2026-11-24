#!/usr/bin/env python3
"""Regression checks for sample attribution and CSV validity/window selection."""
import json
from pathlib import Path
import tempfile
import unittest

from analyze_cpu_resource import analyze_tree, verify_uuid
from analyze_performance_csv import summarize


class ProfileAnalysisTests(unittest.TestCase):
    def test_uuid_mismatch_rejected(self):
        report = json.dumps({"slice_uuid": "AAAA-BBBB"}) + "\n"
        self.assertEqual(verify_uuid(report, "UUID: AAAA-BBBB (arm64) binary"), "AAAA-BBBB")
        with self.assertRaises(ValueError):
            verify_uuid(report, "UUID: CCCC-DDDD (arm64) binary")
        with self.assertRaises(ValueError):
            verify_uuid(report, "UUID: AAAA-BBBB (x86_64) binary")

    def test_recursive_inclusive_weights_not_double_counted(self):
        tree = """Heaviest stack for the target process:
  99  ignored [0x1]
Powerstats for:   Infamous2Game (Test) [1]
  10  pthread [0x1]
    7  spu_exec_thread_proc (in Infamous2Game) + 4 [0x2]
      5  recursive (in Infamous2Game) + 4 [0x3]
        3  recursive (in Infamous2Game) + 8 [0x4]
          3  <e-core>
    2  gameWorker(void*) (in Infamous2Game) + 4 [0x5]
      2  sys_wait (in Infamous2Game) + 4 [0x6]
    1  frame_clock(void*) (in Infamous2Game) + 4 [0x7]
Binary Images:
Powerstats for:   AnotherProcess [2]
  80  ignored [0x8]
"""
        result = analyze_tree(tree, "Infamous2Game")
        self.assertEqual(result["total_samples"], 10)
        self.assertEqual(result["disjoint_role_samples"], {"other": 0, "SPU": 7, "PPU": 2, "renderer": 1})
        counts = {r["function"]: r["samples"] for r in result["exclusive_functions"]}
        self.assertEqual(counts["recursive"], 5)
        self.assertEqual(sum(counts.values()), 10)
        with self.assertRaises(ValueError):
            analyze_tree(tree.replace("    7  spu", "    17  spu"), "Infamous2Game")

    def test_csv_window_validity_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.csv"
            path.write_text("monotonic_s,fps,cpu_percent,cpu_valid,gpu_mean_ms,gpu_samples\n"
                            "0,60,100,1,9,1\n10,3,999,0,0,0\n11,5,200,1,nan,1\n")
            result = summarize(path, "fixture", 1)
            self.assertEqual(result["rows"], 2)
            self.assertEqual(result["metrics"]["fps"]["median"], 4)
            self.assertEqual(result["metrics"]["cpu_percent"]["median"], 200)
            self.assertNotIn("gpu_mean_ms", result["metrics"])
            with self.assertRaises(ValueError):
                summarize(path, "fixture", 0)


if __name__ == "__main__":
    unittest.main()
