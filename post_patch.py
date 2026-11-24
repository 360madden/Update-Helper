"""Run a complete two-capture post-patch evidence cycle; no downstream edits."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import update_helper as u


def cycle(before_path, prefix, expected_host):
    """Use the explicit baseline root, and refuse unstable after-captures."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", prefix):
        raise ValueError("Prefix must be 1-80 letters, digits, underscores or hyphens")
    if u.host() != expected_host.upper():
        raise ValueError("Wrong execution host")
    before_path = Path(before_path).resolve(strict=True)
    before = u.load(before_path)
    u.validate(before)
    if before["host"] != u.host() or before["phase"] != "before":
        raise ValueError("Baseline host or phase mismatch")
    root = Path(before["root"])
    if root.resolve(strict=True) != root or u.HERE.is_relative_to(root):
        raise ValueError("Unsafe or noncanonical baseline root")
    paths = {name: u.HERE / (prefix + "-" + name + ".json")
             for name in ("after-a", "after-b", "consistency", "changes")}
    if any(p.exists() or p.is_symlink() for p in paths.values()):
        raise ValueError("Output already exists; choose a new cycle prefix")

    # Bind the input evidence to its original bytes for later auditing.
    before_digest = hashlib.sha256(before_path.read_bytes()).hexdigest()
    a = u.capture(root, "after", expected_host)
    u.save(paths["after-a"], a)
    b = u.capture(root, "after", expected_host)
    u.save(paths["after-b"], b)
    consistency = u.compare(a, b, allow_same_phase=True)
    consistency["before_manifest_sha256"] = hashlib.sha256(paths["after-a"].read_bytes()).hexdigest()
    consistency["after_manifest_sha256"] = hashlib.sha256(paths["after-b"].read_bytes()).hexdigest()
    u.save(paths["consistency"], consistency)
    if any(consistency["counts"][k] for k in ("added", "removed", "modified")):
        raise ValueError("Post-patch files were not stable; preserve evidence and repeat with a new prefix")
    if hashlib.sha256(before_path.read_bytes()).hexdigest() != before_digest:
        raise ValueError("Baseline changed during this cycle")

    changes = u.compare(before, b)
    changes["before_manifest_sha256"] = before_digest
    changes["after_manifest_sha256"] = consistency["after_manifest_sha256"]
    u.save(paths["changes"], changes)
    return {"status": "stable-comparison-complete", "host": u.host(),
            "counts": changes["counts"], "executable_changed": changes["executable_changed"],
            "outputs": {k: str(v) for k, v in paths.items()}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--prefix", required=True)
    p.add_argument("--expected-host", required=True)
    a = p.parse_args()
    try:
        print(json.dumps(cycle(a.before, a.prefix, a.expected_host), indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
