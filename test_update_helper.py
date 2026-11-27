"""Regression checks use synthetic game files only; never touch the real install."""
import copy
import hashlib
import os
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
        self.assertEqual(c["before_executable_sha256"], hashlib.sha256(b"old").hexdigest())
        self.assertEqual(c["after_executable_sha256"], hashlib.sha256(b"new").hexdigest())
        self.assertEqual(c["before_file_count"], 3)
        self.assertEqual(c["after_file_count"], 3)

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



    def test_duplicate_json_keys_rejected(self):
        p = self.root / "bad.json"
        p.write_bytes(b'{"complete":true,"complete":false}')
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            u.load_hashed(p)

    def test_digest_binds_to_exact_file_bytes(self):
        p = self.root / "exact.json"
        raw = b'{ "hello": 42 }\r\n'
        p.write_bytes(raw)
        obj, digest = u.load_hashed(p)
        self.assertEqual(obj, {"hello": 42})
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_incomplete_publication_never_visible(self):
        p = self.root / "capture.json"
        with patch.object(u, "HERE", self.root.resolve()), patch.object(u.os, "fsync", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                u.save(p, {"test": True})
        self.assertFalse(p.exists())
        self.assertEqual(list(self.root.glob(".uh-*.tmp")), [])

    def test_concurrent_output_creation_never_overwritten(self):
        p = self.root / "capture.json"
        real_link = os.link
        def competing_writer(src, dst):
            Path(dst).write_bytes(b"other writer")
            return real_link(src, dst)
        with patch.object(u, "HERE", self.root.resolve()), patch.object(u.os, "link", competing_writer):
            with self.assertRaises(FileExistsError):
                u.save(p, {"test": True})
        self.assertEqual(p.read_bytes(), b"other writer")
        self.assertEqual(list(self.root.glob(".uh-*.tmp")), [])

    def test_unsafe_output_names_rejected(self):
        with patch.object(u, "HERE", self.root.resolve()):
            for name in ("NUL.json", "evidence.json:stream.json", "bad.txt"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    u.output_path(self.root / name)

    def test_manifest_totals_and_rows_are_strict(self):
        a = self.capture()
        for key in ("bytes", "file_count"):
            b = copy.deepcopy(a)
            b[key] = float(b[key])
            with self.assertRaises(ValueError):
                u.validate(b)
        for rel in ("aux.dat", "a:stream", "alias. ", "bad\x01name"):
            b = copy.deepcopy(a)
            b["files"][0]["path"] = rel
            with self.subTest(rel=rel), self.assertRaises(ValueError):
                u.validate(b)
        b = copy.deepcopy(a)
        b["files"][0] = None
        with self.assertRaisesRegex(ValueError, "Invalid file record"):
            u.validate(b)

    def test_windows_reserved_paths_rejected_on_every_host(self):
        a = self.capture()
        invalid = ("CON.txt", "NUL.tar.gz", "aux .txt", "CONIN$.txt",
                   "conout$", "LPT1.log", "com9", "COM¹.bin", "LPT³",
                   "folder./item", "folder /item", "folder/AUX/item",
                   "folder//item", "./item", "folder/../item",
                   "bad|name", "bad*name", "bad?name", 'bad"name',
                   "bad<name", "bad>name", "bad\x00name", "bad\x1fname")
        for name in invalid:
            b = copy.deepcopy(a)
            b["files"][0]["path"] = name
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Invalid relative path"):
                u.validate(b)

    def test_ordinary_windows_paths_are_not_over_rejected(self):
        a = self.capture()
        # Device-like prefixes and numeric suffixes beyond 1..9 are ordinary
        # filenames; Unicode names and leading dots remain valid evidence.
        for name in ("console.txt", "NUL-extra", "COM10.log", "LPT0.bin",
                     "folder/.cache", "folder/file name.bin", "données.bin"):
            b = copy.deepcopy(a)
            b["files"][0]["path"] = name
            with self.subTest(name=name):
                self.assertIn(name.casefold(), u.validate(b))

    def test_cross_phase_consistency_rejected(self):
        a, b = self.capture(), self.capture("after")
        with self.assertRaisesRegex(ValueError, "same capture phase"):
            u.compare(a, b, True)

    def test_case_only_name_change_is_visible(self):
        a, b = self.capture(), self.capture("after")
        b["files"][0]["path"] = b["files"][0]["path"].upper()
        self.assertEqual(u.compare(a, b)["counts"]["modified"], 1)


if __name__ == "__main__":
    unittest.main()
