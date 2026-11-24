"""Verify complete and intentionally damaged bundles using temporary fixtures."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import post_patch
import update_helper as u
import verify_cycle as v


class VerificationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.game = root / "game"
        self.output = root / "output"
        self.game.mkdir()
        self.output.mkdir()
        self.guard = patch.object(u, "HERE", self.output)
        self.guard.start()
        self.addCleanup(self.guard.stop)
        (self.game / "rift_x64.exe").write_bytes(b"before")
        self.before = self.output / "before.json"
        self.pin = u.save(self.before, u.capture(self.game, "before", u.host()))
        (self.game / "rift_x64.exe").write_bytes(b"after")
        self.prefix = "fixture"
        post_patch.cycle(self.before, self.prefix, u.host(), self.pin)

    def path(self, name):
        return self.output / (self.prefix + "-" + name + ".json")

    def audit(self, pin=None):
        return v.audit(self.before, self.prefix, u.host(), pin or self.pin)

    def rewrite(self, name, callback):
        # Only mutate disposable synthetic fixtures, never operational evidence.
        path = self.path(name)
        doc = u.load(path)
        callback(doc)
        path.write_text(json.dumps(doc), encoding="utf-8")

    def test_success_and_offline_only(self):
        with patch.object(u, "capture", side_effect=AssertionError("No game scan allowed")):
            result = self.audit()
        self.assertEqual(result["status"], "verified-stored-evidence")
        self.assertEqual(result["counts"]["modified"], 1)
        self.assertEqual(len(result["manifest_sha256"]), 5)

    def test_reject_incorrect_baseline_pin(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.audit("0" * 64)

    def test_reject_altered_changes_report(self):
        self.rewrite("changes", lambda d: d["counts"].update(modified=0))
        with self.assertRaisesRegex(ValueError, "Changes report"):
            self.audit()

    def test_reject_altered_consistency_report(self):
        self.rewrite("consistency", lambda d: d["counts"].update(unchanged=999))
        with self.assertRaisesRegex(ValueError, "Consistency report"):
            self.audit()

    def test_reject_after_file_byte_change(self):
        p = self.path("after-a")
        p.write_bytes(p.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "Consistency report"):
            self.audit()

    def test_reject_incomplete_bundle(self):
        self.path("after-b").unlink()
        with self.assertRaises(FileNotFoundError):
            self.audit()

    def test_reject_wrong_evidence_host(self):
        with self.assertRaisesRegex(ValueError, "host or phase mismatch"):
            v.audit(self.before, self.prefix, "wrong", self.pin)

    def test_reject_boolean_in_place_of_integer(self):
        self.rewrite("changes", lambda d: d["counts"].update(modified=True))
        with self.assertRaisesRegex(ValueError, "Changes report"):
            self.audit()

    def test_reject_invalid_prefix(self):
        with self.assertRaisesRegex(ValueError, "Invalid cycle prefix"):
            v.audit(self.before, "../bad", u.host(), self.pin)


if __name__ == "__main__":
    unittest.main()
