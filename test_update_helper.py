"""Regression checks use synthetic game files only; never touch the real install."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import update_helper as u


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "rift_x64.exe").write_bytes(b"old")
        (self.root / "data").mkdir()
        (self.root / "data" / "asset.bin").write_bytes(b"same")
        (self.root / "gone.bin").write_bytes(b"gone")

    def capture(self, phase="before"):
        return u.capture(self.root, phase, u.host())

    def test_hashes_every_regular_file(self):
        m = self.capture()
        self.assertEqual(m["file_count"], 3)
        self.assertEqual(m["bytes"], 11)
        self.assertEqual(u.validate(m)["data/asset.bin"]["sha256"], hashlib.sha256(b"same").hexdigest())

    def test_same_length_content_change_added_removed(self):
        a = self.capture()
        (self.root / "rift_x64.exe").write_bytes(b"new")
        (self.root / "gone.bin").unlink()
        (self.root / "added.bin").write_bytes(b"more")
        b = self.capture("after")
        c = u.compare(a, b)
        self.assertEqual(c["counts"], dict(added=1, removed=1, modified=1, unchanged=1))
        self.assertTrue(c["executable_changed"])

    def test_consistency(self):
        a, b = self.capture(), self.capture()
        self.assertEqual(u.compare(a, b, True)["counts"]["unchanged"], 3)

    def test_wrong_host(self):
        with self.assertRaisesRegex(ValueError, "Wrong host"):
            u.capture(self.root, "before", "INVALID-HOST")

    def test_missing_game_exe(self):
        (self.root / "rift_x64.exe").unlink()
        with self.assertRaisesRegex(ValueError, "Missing rift_x64"):
            self.capture()

    def test_rejects_incomplete(self):
        a = self.capture()
        a["complete"] = False
        with self.assertRaises(ValueError):
            u.validate(a)

    def test_rejects_invalid_hash_and_totals(self):
        a = self.capture()
        b = copy.deepcopy(a)
        b["files"][0]["sha256"] = "invalid"
        with self.assertRaises(ValueError):
            u.validate(b)
        a["file_count"] += 1
        with self.assertRaises(ValueError):
            u.validate(a)

    def test_rejects_case_collision_and_traversal(self):
        a = self.capture()
        b = copy.deepcopy(a)
        b["files"][0]["path"] = "../unsafe"
        with self.assertRaises(ValueError):
            u.validate(b)
        b = copy.deepcopy(a)
        b["files"].append(copy.deepcopy(b["files"][0]))
        b["files"][-1]["path"] = b["files"][-1]["path"].upper()
        with self.assertRaises(ValueError):
            u.validate(b)

    def test_rejects_host_root_and_phase_mismatch(self):
        a, b = self.capture(), self.capture("after")
        for key in ("host", "root"):
            c = copy.deepcopy(b)
            c[key] = "other"
            with self.assertRaises(ValueError):
                u.compare(a, c)
        b["phase"] = "before"
        with self.assertRaises(ValueError):
            u.compare(a, b)

    def test_rejects_reverse_time(self):
        a, b = self.capture(), self.capture("after")
        b["started_utc"] = "2000-01-01T00:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "overlap"):
            u.compare(a, b)

    def test_no_overwrite(self):
        p = self.root / "out.json"
        with patch.object(u, "HERE", self.root.resolve()):
            u.save(p, {"a": 1})
            with self.assertRaises(FileExistsError):
                u.save(p, {"a": 2})
            self.assertEqual(u.load(p), {"a": 1})

    def test_output_restricted(self):
        with self.assertRaisesRegex(ValueError, "Output must"):
            u.save(self.root / "unsafe.json", {})


if __name__ == "__main__":
    unittest.main()
