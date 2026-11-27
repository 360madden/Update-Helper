"""Exercise reporting with disposable evidence; never scan an installed game."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import post_patch
import report_cycle as r
import update_helper as u


class ReportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.game = base / "game"
        self.output = base / "output"
        self.game.mkdir()
        self.output.mkdir()
        guard = patch.object(u, "HERE", self.output)
        guard.start()
        self.addCleanup(guard.stop)
        (self.game / "rift_x64.exe").write_bytes(b"before-exe")
        (self.game / "Assets").mkdir()
        (self.game / "Assets" / "assets.001").write_bytes(b"before-assets")
        (self.game / "old.txt").write_bytes(b"removed")
        (self.game / "manifest64.txt").write_bytes(b"manifest-before")
        (self.game / "unchanged.txt").write_bytes(b"same")
        self.before = self.output / "before.json"
        self.pin = u.save(self.before, u.capture(self.game, "before", u.host()))
        self.prefix = "fixture"

    def complete_cycle(self, changed=True):
        if changed:
            (self.game / "rift_x64.exe").write_bytes(b"after-exe")
            (self.game / "Assets" / "assets.001").write_bytes(b"after-assets")
            (self.game / "old.txt").unlink()
            (self.game / "manifest64.txt").write_bytes(b"manifest-after")
            (self.game / "Interface").mkdir()
            (self.game / "Interface" / "example.lua").write_bytes(b"new-interface")
        post_patch.cycle(self.before, self.prefix, u.host(), self.pin)

    def path(self, name):
        return self.output / f"{self.prefix}-{name}.json"

    def render(self, pin=None):
        return r.render_cycle(self.before, self.prefix, u.host(), pin or self.pin)

    def arguments(self, target=None):
        args = ["--before", str(self.before), "--prefix", self.prefix,
                "--expected-evidence-host", u.host(),
                "--expected-before-sha256", self.pin]
        if target is not None:
            args += ["--out", str(target)]
        return args

    def snapshot_bytes(self):
        return {p.name: p.read_bytes() for p in self.output.glob("*.json")}

    def test_reports_verified_changes_and_all_pins_without_game_access(self):
        self.complete_cycle()
        original = self.snapshot_bytes()
        with patch.object(u, "capture", side_effect=AssertionError("No live scan")):
            text = self.render()
        self.assertIn("| 1 | 1 | 3 | 1 |", text)
        self.assertIn("content SHA-256: changed", text)
        self.assertIn("### Removed: old.txt", text)
        self.assertIn("### Added: Interface/example.lua", text)
        self.assertIn("Asset / data", text)
        self.assertIn("Manifest / configuration", text)
        self.assertIn("filename-based routing hints", text)
        self.assertIn("does not establish live game behavior", text)
        self.assertIn(self.pin, text)
        for name in ("after-a", "after-b", "consistency", "changes"):
            self.assertIn(u.load_hashed(self.path(name))[1], text)
        for doc in (u.load(self.before), u.load(self.path("after-a")), u.load(self.path("after-b"))):
            self.assertIn(doc["started_utc"], text)
            self.assertIn(doc["finished_utc"], text)
        for change in u.load(self.path("changes"))["changes"]:
            for side in ("before", "after"):
                if change[side] is not None:
                    self.assertIn(change[side]["sha256"], text)
        self.assertEqual(self.snapshot_bytes(), original)

    def test_no_change_report_preserves_uncertainty(self):
        self.complete_cycle(changed=False)
        text = self.render()
        self.assertIn("| 0 | 0 | 0 | 5 |", text)
        self.assertIn("content SHA-256: unchanged", text)
        self.assertIn("No installation-file differences were observed", text)
        self.assertIn("does not establish that servers did not update", text)
        self.assertNotIn("Suggested review", text)

    def test_rejects_tampered_report_and_incomplete_bundle(self):
        self.complete_cycle()
        changes = self.path("changes")
        raw = changes.read_bytes()
        doc = u.load(changes)
        doc["counts"]["modified"] = 0
        changes.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Changes report"):
            self.render()
        changes.write_bytes(raw)
        self.path("after-a").unlink()
        with self.assertRaises(FileNotFoundError):
            self.render()

    def test_rejects_self_consistent_unstable_after_captures(self):
        self.complete_cycle()
        a, a_pin = u.load_hashed(self.path("after-a"))
        b = u.load(self.path("after-b"))
        b["files"][0]["sha256"] = "0" * 64
        self.path("after-b").write_text(json.dumps(b), encoding="utf-8")
        _, b_pin = u.load_hashed(self.path("after-b"))
        agreement = u.compare(a, b, allow_same_phase=True)
        agreement["before_manifest_sha256"] = a_pin
        agreement["after_manifest_sha256"] = b_pin
        self.path("consistency").write_text(json.dumps(agreement), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not stable"):
            self.render()

    def test_changed_evidence_after_audit_or_during_render_is_refused(self):
        self.complete_cycle()
        real_audit = r.v.audit

        def changed_after_audit(*args):
            verified = real_audit(*args)
            path = self.path("changes")
            path.write_bytes(path.read_bytes() + b" ")
            return verified

        original = self.path("changes").read_bytes()
        with patch.object(r.v, "audit", changed_after_audit):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                self.render()
        self.path("changes").write_bytes(original)
        real_render = r._render

        def changed_while_rendering(*args):
            text = real_render(*args)
            self.before.write_bytes(self.before.read_bytes() + b" ")
            return text

        with patch.object(r, "_render", changed_while_rendering):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                self.render()

    def test_markdown_names_are_literal(self):
        value = "[click](https://example.test) | *title* <script>\nnext"
        escaped = r.cell(value)
        self.assertNotIn("<script>", escaped)
        self.assertNotIn("\n", escaped)
        self.assertIn(r"\[click\]", escaped)
        self.assertIn(r"\|", escaped)
        self.assertIn("&lt;script&gt;", escaped)
        self.assertIn(r"\\u000a", escaped)

    def test_safe_output_and_existing_output_cannot_be_overwritten(self):
        for name in ("../escape.md", "bad.json", "CON.md", "lpt1.md", "bad:stream.md"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                r.save_report(self.output / name, "text")
        target = self.output / "report.md"
        digest = r.save_report(target, "complete\n")
        self.assertEqual(digest, hashlib.sha256(b"complete\n").hexdigest())
        with self.assertRaises(FileExistsError):
            r.save_report(target, "replacement")
        self.assertEqual(target.read_bytes(), b"complete\n")

    def test_atomic_publication_race_and_failure_clean_up(self):
        target = self.output / "race.md"
        real_link = r.os.link

        def rival_wins(source, destination):
            Path(destination).write_bytes(b"rival")
            real_link(source, destination)

        with patch.object(r.os, "link", rival_wins):
            with self.assertRaises(FileExistsError):
                r.save_report(target, "our report")
        self.assertEqual(target.read_bytes(), b"rival")
        self.assertEqual(list(self.output.glob(".uh-report-*.tmp")), [])
        failed = self.output / "failure.md"
        with patch.object(r.os, "link", side_effect=OSError("link unavailable")):
            with self.assertRaisesRegex(OSError, "link unavailable"):
                r.save_report(failed, "our report")
        self.assertFalse(failed.exists())
        self.assertEqual(list(self.output.glob(".uh-report-*.tmp")), [])

    def test_cli_stdout_file_and_invalid_pin_exit(self):
        self.complete_cycle()
        before = self.snapshot_bytes()
        out = io.StringIO()
        with patch("sys.stdout", out):
            self.assertEqual(r.main(self.arguments()), 0)
        self.assertTrue(out.getvalue().startswith("# Update Helper"))
        target = self.output / "report.md"
        with patch("sys.stdout", io.StringIO()) as output:
            self.assertEqual(r.main(self.arguments(target)), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "verified-report-written")
        self.assertEqual(result["sha256"], hashlib.sha256(target.read_bytes()).hexdigest())
        invalid_target = self.output / "invalid.md"
        args = self.arguments(invalid_target)
        args[args.index("--expected-before-sha256") + 1] = "0" * 64
        with patch("sys.stderr", io.StringIO()) as error:
            self.assertEqual(r.main(args), 2)
        self.assertIn("SHA-256 mismatch", error.getvalue())
        self.assertFalse(invalid_target.exists())
        self.assertEqual(before, self.snapshot_bytes())


if __name__ == "__main__":
    unittest.main()
