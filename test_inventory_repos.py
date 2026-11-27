"""Repository discovery fixtures never inspect or change real downstream repos."""
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import inventory_repos as inv
import update_helper as u


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.empty_config = self.root / "empty.gitconfig"
        self.empty_config.write_bytes(b"")
        self.empty_hooks = self.root / "empty-hooks"
        self.empty_hooks.mkdir()

    def fixture_git(self, directory, *args):
        """Keep setup writes inside fixtures, even under an IDE's Git routing.

        Explicit cwd alone does not override GIT_DIR, GIT_WORK_TREE, or an
        alternate index. Strip all inherited Git controls before synthetic
        init/add/commit/checkout commands, and isolate configuration, templates,
        hooks, and signing from the user's real Git installation. Empty regular
        config files work on Windows and POSIX without special device paths.
        """
        environment = {k: v for k, v in os.environ.items()
                       if not k.upper().startswith("GIT_")}
        environment.update(GIT_CONFIG_GLOBAL=str(self.empty_config),
                           GIT_CONFIG_SYSTEM=str(self.empty_config),
                           GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
        command = [shutil.which("git"), "-c", "core.hooksPath=" + str(self.empty_hooks),
                   "-c", "init.templateDir=" + str(self.empty_hooks),
                   "-c", "commit.gpgsign=false", *args]
        return subprocess.run(command, cwd=directory, env=environment,
                              stdin=subprocess.DEVNULL, check=True,
                              capture_output=True, timeout=5)

    def candidate(self, name, gitfile=False):
        directory = self.root / name
        directory.mkdir(parents=True)
        if gitfile:
            (directory / ".git").write_text("gitdir: /outside/discovery\n", encoding="utf-8")
        else:
            (directory / ".git").mkdir()
        return directory

    @staticmethod
    def metadata(git, directory, arguments, timeout, **kwargs):
        return "a" * 40 if "--verify" in arguments else "refs/heads/main"

    def test_shallow_discovery_reference_policy_and_unknown_clean_state(self):
        self.candidate("project")
        self.candidate("TeLaRaFlY")
        self.candidate("container/nested")
        with patch.object(inv, "git_value", side_effect=self.metadata), patch.object(inv.shutil, "which", return_value="git"):
            result = inv.inventory(self.root, u.host())
        self.assertTrue(result["complete"])
        self.assertEqual([r["repository"] for r in result["repositories"]], ["project", "TeLaRaFlY"])
        for row in result["repositories"]:
            self.assertIsNone(row["clean"])
            self.assertIsNone(row["changed_entries"])
            self.assertFalse(row["status_inspected"])
            self.assertEqual(row["head"], "a" * 40)
            self.assertEqual(row["branch"], "main")
        self.assertTrue(result["repositories"][1]["reference_only"])

    def test_gitfile_target_is_not_followed(self):
        self.candidate("worktree", gitfile=True)
        with patch.object(inv, "git_value") as run:
            result = inv.inventory(self.root, u.host())
        run.assert_not_called()
        self.assertFalse(result["complete"])
        self.assertEqual(result["repositories"][0]["git_marker"], "gitfile")
        self.assertIsNone(result["repositories"][0]["head"])

    def test_linked_candidate_or_git_marker_is_not_traversed(self):
        self.candidate("ordinary")
        linked = self.root / "linked"
        linked.mkdir()
        real_stat = u.safe_stat
        def refuse(path):
            if path == linked or path == self.root / "ordinary" / ".git":
                raise ValueError("Reparse point or symlink refused")
            return real_stat(path)
        with patch.object(u, "safe_stat", side_effect=refuse), patch.object(inv, "git_value") as run:
            result = inv.inventory(self.root, u.host())
        run.assert_not_called()
        self.assertFalse(result["complete"])
        self.assertEqual(result["repository_count"], 0)
        self.assertEqual(len(result["skipped_entries"]), 2)

    def test_wrong_host_fails_before_discovery(self):
        with patch.object(inv.shutil, "which") as find:
            with self.assertRaisesRegex(ValueError, "Wrong host"):
                inv.inventory(self.root, "NOT-THIS-HOST")
        find.assert_not_called()

    @unittest.skipUnless(shutil.which("git"), "Git required for metadata integration fixture")
    def test_unborn_branch_is_retained_without_claiming_valid_head(self):
        directory = self.root / "unborn"
        self.fixture_git(self.root, "init", "-b", "main", str(directory))
        result = inv.inventory(self.root, u.host())
        row = result["repositories"][0]
        self.assertEqual(row["branch"], "main")
        self.assertIsNone(row["head"])
        self.assertFalse(result["complete"])
        self.assertIsNone(row["clean"])

    def test_missing_git_and_timeout_never_claim_clean_or_complete(self):
        self.candidate("project")
        with patch.object(inv.shutil, "which", return_value=None):
            missing = inv.inventory(self.root, u.host())
        self.assertFalse(missing["complete"])
        with patch.object(inv.shutil, "which", return_value="git"), patch.object(inv, "git_value", side_effect=subprocess.TimeoutExpired("git", 1)):
            timed_out = inv.inventory(self.root, u.host())
        row = timed_out["repositories"][0]
        self.assertFalse(timed_out["complete"])
        self.assertIsNone(row["clean"])
        self.assertIsNone(row["head"])
        self.assertEqual(len(row["errors"]), 2)

    def test_git_environment_isolation_and_nonzero_failure(self):
        directory = self.candidate("project")
        failed = subprocess.CompletedProcess([], 128, b"", b"bad repository")
        with patch.dict(os.environ, {"GIT_DIR": "/elsewhere", "GIT_INDEX_FILE": "/elsewhere/index"}), patch.object(inv.subprocess, "run", return_value=failed) as run:
            with self.assertRaisesRegex(ValueError, "Git exited 128"):
                inv.git_value("git", directory, ["rev-parse", "HEAD"], 3)
        args, options = run.call_args
        self.assertIn("--no-optional-locks", args[0])
        self.assertIn("core.fsmonitor=false", args[0])
        self.assertNotIn("GIT_DIR", options["env"])
        self.assertNotIn("GIT_INDEX_FILE", options["env"])
        self.assertEqual(options["timeout"], 3)

    def test_partial_inventory_is_saved_immutably_and_returns_failure(self):
        self.candidate("linked-worktree", gitfile=True)
        out = self.root / "inventory.json"
        arguments = ["inventory_repos.py", "--root", str(self.root), "--expected-host", u.host(), "--out", str(out)]
        with patch.object(u, "HERE", self.root), patch.object(sys, "argv", arguments), patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(inv.main(), 2)
            original = out.read_bytes()
            self.assertEqual(inv.main(), 2)
        self.assertEqual(out.read_bytes(), original)
        self.assertFalse(u.load(out)["complete"])

    @unittest.skipUnless(shutil.which("git"), "Git required for metadata integration fixture")
    def test_real_git_metadata_preserves_worktree_and_index(self):
        directory = self.root / "real"
        directory.mkdir()
        def git(*args):
            return self.fixture_git(directory, *args)
        git("init", "-b", "main")
        (directory / "tracked.txt").write_text("original\n", encoding="utf-8")
        git("add", "tracked.txt")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-m", "fixture")
        index_before = (directory / ".git" / "index").read_bytes()
        (directory / "tracked.txt").write_text("changed\n", encoding="utf-8")
        result = inv.inventory(self.root, u.host())
        row = result["repositories"][0]
        self.assertTrue(result["complete"])
        self.assertEqual(row["branch"], "main")
        self.assertEqual(row["head"], git("rev-parse", "HEAD").stdout.decode().strip())
        self.assertIsNone(row["clean"])
        self.assertEqual((directory / ".git" / "index").read_bytes(), index_before)
        self.assertEqual((directory / "tracked.txt").read_text(), "changed\n")
        git("checkout", "--detach")
        detached = inv.inventory(self.root, u.host())["repositories"][0]
        self.assertEqual(detached["branch"], "(detached)")
        self.assertTrue(detached["metadata_complete"])

    @unittest.skipUnless(shutil.which("git"), "Git required for fixture isolation regression")
    def test_fixture_setup_ignores_inherited_git_routing_and_hooks(self):
        # Reproduce the actual failure mode in a child test process: inherited
        # Git routing once made a supposedly temporary fixture commit an
        # unrelated repository's dirty tracked file. Both repositories here
        # are disposable; a successful child must leave the decoy unchanged.
        decoy = self.root / "decoy"
        decoy.mkdir()
        self.fixture_git(decoy, "init", "-b", "main")
        tracked = decoy / "tracked.txt"
        tracked.write_text("decoy original\n", encoding="utf-8")
        self.fixture_git(decoy, "add", "tracked.txt")
        self.fixture_git(decoy, "-c", "user.name=Fixture", "-c",
                         "user.email=fixture@example.invalid", "commit", "-m", "decoy baseline")
        head_before = self.fixture_git(decoy, "rev-parse", "HEAD").stdout
        index_before = (decoy / ".git" / "index").read_bytes()
        tracked.write_text("decoy unstaged change\n", encoding="utf-8")
        worktree_before = tracked.read_bytes()
        external_hooks = self.root / "external-hooks"
        external_hooks.mkdir()
        hook = external_hooks / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        hook.chmod(0o755)
        external_config = self.root / "external.gitconfig"
        external_config.write_text("[commit]\n\tgpgsign = true\n", encoding="utf-8")
        environment = dict(os.environ)
        environment.update(GIT_DIR=str(decoy / ".git"), GIT_WORK_TREE=str(decoy),
                           GIT_INDEX_FILE=str(decoy / ".git" / "index"),
                           GIT_CONFIG_GLOBAL=str(external_config),
                           GIT_CONFIG_SYSTEM=str(external_config),
                           GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="core.hooksPath",
                           GIT_CONFIG_VALUE_0=str(external_hooks))
        child = subprocess.run(
            [sys.executable, "-B", "-m", "unittest", "-q",
             "test_inventory_repos.InventoryTests.test_real_git_metadata_preserves_worktree_and_index",
             "test_inventory_repos.InventoryTests.test_unborn_branch_is_retained_without_claiming_valid_head"],
            cwd=Path(__file__).resolve().parent, env=environment,
            stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr.decode("utf-8", errors="replace"))
        self.assertEqual(self.fixture_git(decoy, "rev-parse", "HEAD").stdout, head_before)
        self.assertEqual((decoy / ".git" / "index").read_bytes(), index_before)
        self.assertEqual(tracked.read_bytes(), worktree_before)


if __name__ == "__main__":
    unittest.main()
