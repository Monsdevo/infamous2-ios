"""Offline regression for partial-file resume and the readiness barrier."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import transfer_bces_ios as transfer


class ResumeTests(unittest.TestCase):
    def exercise(self, *, capacity=2 * 1024**3, final_bad=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            resources = root / "build/bces01229/ios-prepared/resources"
            resources.mkdir(parents=True)
            game = root / "data/game/BCES01229"
            game.mkdir(parents=True)
            (game / "complete").write_bytes(b"complete")
            (game / "partial").write_bytes(b"replaced")
            manifest = {"total_bytes": 16, "profile": "fixture", "entries": [
                {"path": "PS3_GAME/complete", "bytes": 8},
                {"path": "PS3_GAME/partial", "bytes": 8}]}
            (resources / "bces-inputs.json").write_text(json.dumps(manifest))
            copied = []
            listing_count = 0

            def run(args, **kwargs):
                nonlocal listing_count
                if "from" in args:
                    dest = Path(args[args.index("--destination") + 1])
                    dest.write_text(json.dumps({"link_validation_passed": True,
                        "bundled_ELF_verified": True, "available_capacity_bytes": capacity}))
                elif "files" in args:
                    listing_count += 1
                    size = 2 if listing_count == 1 or final_bad else 8
                    dest = Path(args[args.index("--json-output") + 1])
                    dest.write_text(json.dumps({"result": {"files": [
                        {"relativePath": "PS3_GAME/complete", "metadata": {"size": 8}, "resources": {"isDirectory": False}},
                        {"relativePath": "PS3_GAME/partial", "metadata": {"size": size}, "resources": {"isDirectory": False}}]}}))
                elif "to" in args:
                    src = Path(args[args.index("--source") + 1])
                    copied.append(src.name)
                    if src.is_dir():
                        self.assertEqual([p.name for p in src.iterdir()], ["partial"])
                        self.assertEqual((src / "partial").read_bytes(), b"replaced")
                        self.assertEqual((src / "partial").stat().st_ino, (game / "partial").stat().st_ino)
                return subprocess.CompletedProcess(args, 0)

            failure = None
            with patch.object(transfer, "ROOT", root), patch.object(transfer.subprocess, "run", run), patch("sys.argv", ["transfer", "--device", "fixture", "--resume"]):
                try:
                    transfer.main()
                except SystemExit as exc:
                    failure = str(exc)
            state_path = root / "out/step12-asset-transfer/state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else None
            return copied, failure, state

    def test_resume_replaces_partial_and_preserves_complete(self):
        copied, failure, state = self.exercise()
        self.assertIsNone(failure)
        self.assertEqual(copied, ["PS3_GAME", "transfer-complete.json"])
        self.assertEqual(state["retained_size_matching_bytes"], 8)
        self.assertEqual(state["selected_bytes"], 8)
        self.assertTrue(state["complete"])

    def test_insufficient_headroom_never_copies(self):
        copied, failure, _ = self.exercise(capacity=8)
        self.assertIn("Not enough", failure)
        self.assertEqual(copied, [])

    def test_failed_final_inventory_never_publishes_token(self):
        copied, failure, state = self.exercise(final_bad=True)
        self.assertIn("no readiness token", failure)
        self.assertEqual(copied, ["PS3_GAME"])
        self.assertFalse(state["complete"])


if __name__ == "__main__":
    unittest.main()
