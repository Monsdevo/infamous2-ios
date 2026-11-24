#!/usr/bin/env python3
import unittest
from pathlib import Path
from build_bces_spu_variant import variant_command


class VariantCommandTests(unittest.TestCase):
    def test_only_optimization_and_output_change(self):
        original = ["clang", "-O1", "-fno-strict-aliasing", "-fwrapv",
                    "-ffp-contract=off", "-c", "spu.c", "-o", "baseline.o"]
        changed = variant_command(original, Path("variant.o"))
        self.assertEqual([i for i, (a, b) in enumerate(zip(original, changed)) if a != b], [1, 8])
        self.assertEqual(changed[1], "-O2")
        self.assertEqual(original[-1], "baseline.o")

    def test_ambiguous_flags_fail_closed(self):
        for command in (["clang", "-O3", "-o", "x"],
                        ["clang", "-O1", "-O2", "-o", "x"],
                        ["clang", "-O1", "-o", "x", "-o", "y"]):
            with self.assertRaises(ValueError):
                variant_command(command, Path("variant.o"))


if __name__ == "__main__":
    unittest.main()
