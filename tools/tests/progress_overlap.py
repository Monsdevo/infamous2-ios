import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_progress_overlap import merged, length, overlap


class ProgressOverlap(unittest.TestCase):
    def test_clips_and_merges_nested_intervals(self):
        self.assertEqual(merged([(0, 3), (1, 2), (4, 5)], .5, 4.5), [(.5, 3), (4, 4.5)])

    def test_joint_overlap_and_remainder(self):
        drain = merged([(0, 2), (4, 6)], 0, 6)
        poll = merged([(1, 5), (2, 3)], 0, 6)
        self.assertEqual(overlap(drain, poll), 2)
        self.assertEqual(length(poll)-overlap(drain, poll), 2)

    def test_empty_touching_and_outside(self):
        self.assertEqual(merged([(-2, -1), (1, 2), (3, 3)], 2, 3), [])
        self.assertEqual(overlap([(0, 1)], [(1, 2)]), 0)
        self.assertEqual(overlap([], [(0, 1)]), 0)


if __name__ == '__main__':
    unittest.main()
