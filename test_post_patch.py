"""Exercise the complete cycle with synthetic files, not the live client."""
import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import post_patch
import update_helper as u


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.game = base / "game"
        self.output = base / "output"
        self.game.mkdir()
        self.output.mkdir()
        (self.game / "rift_x64.exe").write_bytes(b"old")
        self.base = self.output / "before.json"
        self.guard = patch.object(u, "HERE", self.output)
        self.guard.start()
        self.addCleanup(self.guard.stop)
        self.pin = u.save(self.base, u.capture(self.game, "before", u.host()))

    def test_success(self):
        (self.game / "rift_x64.exe").write_bytes(b"new")
        report = post_patch.cycle(self.base, "test", u.host(), self.pin)
        self.assertEqual(report["counts"]["modified"], 1)
        self.assertTrue(report["executable_changed"])
        changes = u.load(self.output / "test-changes.json")
        self.assertEqual(changes["consistency_manifest_sha256"], u.load_hashed(self.output / "test-consistency.json")[1])
        self.assertEqual(changes["before_manifest_sha256"], self.pin)
        self.assertEqual(u.load(self.output / "test-consistency.json")["counts"]["unchanged"], 1)
        with self.assertRaisesRegex(ValueError, "already exists"):
            post_patch.cycle(self.base, "test", u.host(), self.pin)

    def test_refuse_unstable_after(self):
        real = u.capture
        calls = 0
        def changing(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                (self.game / "rift_x64.exe").write_bytes(b"new")
            return real(*args)
        with patch.object(u, "capture", changing):
            with self.assertRaisesRegex(ValueError, "not stable"):
                post_patch.cycle(self.base, "unstable", u.host(), self.pin)
        self.assertTrue((self.output / "unstable-consistency.json").exists())
        self.assertFalse((self.output / "unstable-changes.json").exists())

    def test_reject_wrong_host_and_bad_prefix(self):
        with self.assertRaisesRegex(ValueError, "Wrong execution host"):
            post_patch.cycle(self.base, "test", "wrong-host", self.pin)
        with self.assertRaisesRegex(ValueError, "Prefix"):
            post_patch.cycle(self.base, "../escape", u.host(), self.pin)



    def test_wrong_pin_fails_before_capture(self):
        with patch.object(u, "capture") as capture:
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                post_patch.cycle(self.base, "pin", u.host(), "0" * 64)
            capture.assert_not_called()
        self.assertFalse((self.output / "pin-after-a.json").exists())

    def test_baseline_changed_midcycle_refuses_report(self):
        real = u.capture
        def changing(*args):
            result = real(*args)
            self.base.write_bytes(self.base.read_bytes() + b" ")
            return result
        with patch.object(u, "capture", changing):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                post_patch.cycle(self.base, "edited", u.host(), self.pin)
        self.assertFalse((self.output / "edited-changes.json").exists())

    def test_modified_saved_capture_refuses_report(self):
        real = u.save
        def changing(path, obj):
            digest = real(path, obj)
            if Path(path).name.endswith("-after-a.json"):
                Path(path).write_bytes(Path(path).read_bytes() + b" ")
            return digest
        with patch.object(u, "save", changing):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                post_patch.cycle(self.base, "edited-capture", u.host(), self.pin)
        self.assertFalse((self.output / "edited-capture-changes.json").exists())

    def test_first_capture_overlaps_baseline_refuses_report(self):
        baseline_finished = dt.datetime.fromisoformat(u.load(self.base)["finished_utc"])
        real = u.capture
        calls = 0

        def clock_rollback(*args):
            nonlocal calls
            calls += 1
            result = real(*args)
            if calls == 1:
                # Reproduce a wall-clock adjustment during only the first
                # capture. The second capture alone still compares cleanly.
                result["started_utc"] = (baseline_finished - dt.timedelta(seconds=1)).isoformat()
            return result

        with patch.object(u, "capture", clock_rollback):
            with self.assertRaisesRegex(ValueError, "overlap or are out of order"):
                post_patch.cycle(self.base, "clock-rollback", u.host(), self.pin)
        self.assertTrue((self.output / "clock-rollback-after-a.json").exists())
        self.assertTrue((self.output / "clock-rollback-after-b.json").exists())
        self.assertFalse((self.output / "clock-rollback-changes.json").exists())


if __name__ == "__main__":
    unittest.main()
