"""Record immediate-child Git repository candidates without changing them.

This is a local routing inventory, not a list of confirmed RIFT consumers.
Git metadata is observed independently; no worktree status, fetch, recursive
search, game access, or downstream write is performed.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

import update_helper as u


SCHEMA = "update-helper.repo-inventory.v2"


def git_value(git, directory, arguments, timeout, allow_missing=False):
    """Bound one metadata-only Git read and discard inherited repository routing.

    Supplying --git-dir prevents accidental discovery of a parent repository.
    Optional locks and fsmonitor are disabled even though these plumbing reads
    do not refresh the index. No status scan means no recursive worktree reads
    or configured clean filters. A failed command always leaves metadata unknown.
    """
    environment = {k: v for k, v in os.environ.items()
                   if not k.upper().startswith("GIT_")}
    environment.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
                       GIT_NO_LAZY_FETCH="1")
    command = [git, "--no-optional-locks", "-c", "core.fsmonitor=false",
               "--git-dir=" + str(directory / ".git"), *arguments]
    result = subprocess.run(command, cwd=directory, env=environment,
                            stdin=subprocess.DEVNULL, capture_output=True,
                            timeout=timeout, check=False)
    if allow_missing and result.returncode == 1 and not result.stdout and not result.stderr:
        # symbolic-ref --quiet returns 1 without diagnostics for detached HEAD.
        # This exception is opt-in; other failures still remain failures.
        return None
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[:1000]
        raise ValueError(f"Git exited {result.returncode}" + (f": {detail}" if detail else ""))
    value = result.stdout.decode("utf-8", errors="strict").strip()
    if not value or "\n" in value or "\r" in value or len(value) > 4096:
        raise ValueError("Unexpected Git metadata response")
    return value


def inspect_repository(directory, marker_kind, git, timeout):
    row = {"repository": directory.name, "path": str(directory),
           "git_marker": marker_kind, "head": None, "branch": None,
           "clean": None, "changed_entries": None, "status_inspected": False,
           "reference_only": directory.name.casefold() == "telarafly",
           "metadata_complete": False, "errors": []}
    if marker_kind != "directory":
        # Gitfiles also occur for submodules; do not call every file marker a
        # worktree or follow a path that may leave the explicit discovery root.
        row["errors"].append("Gitfile target not followed; Git metadata not inspected")
        return row
    if git is None:
        row["errors"].append("Git executable unavailable; Git metadata not inspected")
        return row
    try:
        head = git_value(git, directory, ["rev-parse", "--verify", "--quiet", "HEAD"], timeout)
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head):
            raise ValueError("HEAD did not resolve to a Git object ID")
        row["head"] = head
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        # Exit 1 can mean an unborn branch. Do not silently interpret every
        # unresolved HEAD as an empty, healthy repository.
        row["errors"].append(f"HEAD unresolved (possibly unborn): {error}")
    try:
        # symbolic-ref also preserves the branch name for an unborn repository,
        # whose HEAD object cannot yet resolve. Quiet exit 1 identifies detached
        # HEAD only if the independent object lookup succeeded.
        branch = git_value(git, directory, ["symbolic-ref", "--quiet", "HEAD"],
                           timeout, allow_missing=True)
        if branch is None and row["head"] is not None:
            row["branch"] = "(detached)"
        elif isinstance(branch, str) and branch.startswith("refs/heads/") and branch[11:]:
            row["branch"] = branch[11:]
        else:
            raise ValueError("Branch is not an observed local branch or detached HEAD")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        row["errors"].append(f"Branch unresolved: {error}")
    row["metadata_complete"] = not row["errors"]
    return row


def inventory(root, expected_host, timeout=5):
    """Inspect one explicit root; linked entries are recorded and never entered."""
    if u.host() != expected_host.upper():
        raise ValueError(f"Wrong host: expected {expected_host}, got {u.host()}")
    if type(timeout) is not int or not 1 <= timeout <= 30:
        raise ValueError("Git timeout must be an integer from 1 to 30 seconds")
    root = Path(root).absolute()
    for component in reversed([root, *root.parents]):
        u.safe_stat(component)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Inventory root must be a directory")
    started = u.utc()
    repositories, skipped = [], []
    git = shutil.which("git")
    for directory in sorted(root.iterdir(), key=lambda item: (item.name.casefold(), item.name)):
        try:
            info = u.safe_stat(directory)
        except (OSError, ValueError) as error:
            skipped.append({"entry": directory.name, "reason": str(error)})
            continue
        if not stat.S_ISDIR(info.st_mode):
            continue
        marker = directory / ".git"
        try:
            marker_stat = u.safe_stat(marker)
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as error:
            skipped.append({"entry": directory.name, "reason": f"Git marker refused: {error}"})
            continue
        if stat.S_ISDIR(marker_stat.st_mode):
            marker_kind = "directory"
        elif stat.S_ISREG(marker_stat.st_mode):
            marker_kind = "gitfile"
        else:
            skipped.append({"entry": directory.name, "reason": "Git marker is not a regular file or directory"})
            continue
        repositories.append(inspect_repository(directory, marker_kind, git, timeout))
    return {"schema": SCHEMA, "host": u.host(), "root": str(root),
            "started_utc": started, "finished_utc": u.utc(),
            "complete": not skipped and all(r["metadata_complete"] for r in repositories),
            "repository_count": len(repositories), "repositories": repositories,
            "skipped_entries": skipped,
            "scope": "Immediate-child .git markers only; no recursion or linked marker targets. "
                     "Metadata observations are not atomic. Worktree status was not inspected; "
                     "clean/changed_entries are unknown. Presence does not establish a RIFT recovery target."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--git-timeout", type=int, default=5,
                        help="Maximum seconds per metadata read (1-30; default 5)")
    args = parser.parse_args()
    try:
        u.output_path(args.out)
        result = inventory(args.root, args.expected_host, args.git_timeout)
        sha = u.save(args.out, result)
        print(json.dumps({"out": str(args.out), "sha256": sha,
                          "repository_count": result["repository_count"],
                          "complete": result["complete"]}, indent=2))
        # Preserve a partial inventory for review, but never advertise complete
        # success when an entry or its metadata could not be inspected.
        return 0 if result["complete"] else 2
    except (OSError, ValueError, TypeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
