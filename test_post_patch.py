"""Exercise the complete cycle with synthetic files, not the live client."""
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
        u.save(self.base, u.capture(self.game, "before", u.host()))

    def test_success(self):
        (self.game / "rift_x64.exe").write_bytes(b"new")
        report = post_patch.cycle(self.base, "test", u.host())
        self.assertEqual(report["counts"]["modified"], 1)
        self.assertTrue(report["executable_changed"])
        self.assertEqual(u.load(self.output / "test-consistency.json")["counts"]["unchanged"], 1)
        with self.assertRaisesRegex(ValueError, "already exists"):
            post_patch.cycle(self.base, "test", u.host())

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
                post_patch.cycle(self.base, "unstable", u.host())
        self.assertTrue((self.output / "unstable-consistency.json").exists())
        self.assertFalse((self.output / "unstable-changes.json").exists())

    def test_reject_wrong_host_and_bad_prefix(self):
        with self.assertRaisesRegex(ValueError, "Wrong execution host"):
            post_patch.cycle(self.base, "test", "wrong-host")
        with self.assertRaisesRegex(ValueError, "Prefix"):
            post_patch.cycle(self.base, "../escape", u.host())


if __name__ == "__main__":
    unittest.main()
