"""Run a complete two-capture post-patch evidence cycle; no downstream edits."""
import argparse
import json
from pathlib import Path
import re
import sys

import update_helper as u


def cycle(before_path, prefix, expected_host, expected_before_sha256):
    """Use the explicit baseline root, and refuse unstable after-captures."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", prefix):
        raise ValueError("Prefix must be 1-80 letters, digits, underscores or hyphens")
    if u.host() != expected_host.upper():
        raise ValueError("Wrong execution host")
    before_path = Path(before_path).resolve(strict=True)
    # The trusted pre-patch digest must be supplied independently of the file.
    # Read and parse a single byte sequence, then validate its pinned identity.
    if expected_before_sha256 is None:
        raise ValueError("A pinned pre-patch SHA-256 is required")
    before, before_digest = u.load_hashed(before_path)
    u.check_pin(before_digest, expected_before_sha256)
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
    for p in paths.values():
        u.output_path(p)

    # Publish each capture exclusively, then re-read the exact stored bytes.
    # Do not report provenance for a file that no longer matches the capture.
    a_sha = u.save(paths["after-a"], u.capture(root, "after", expected_host))
    b_sha = u.save(paths["after-b"], u.capture(root, "after", expected_host))
    a, observed_a = u.load_hashed(paths["after-a"])
    b, observed_b = u.load_hashed(paths["after-b"])
    u.check_pin(observed_a, a_sha)
    u.check_pin(observed_b, b_sha)
    consistency = u.compare(a, b, allow_same_phase=True)
    consistency["before_manifest_sha256"] = a_sha
    consistency["after_manifest_sha256"] = b_sha
    consistency_sha = u.save(paths["consistency"], consistency)
    if any(consistency["counts"][k] for k in ("added", "removed", "modified")):
        raise ValueError("Post-patch files were not stable; preserve evidence and repeat with a new prefix")
    # Recheck all immutable inputs and the consistency report immediately before final publication.
    for evidence, expected in ((before_path, before_digest), (paths["after-a"], a_sha),
                               (paths["after-b"], b_sha), (paths["consistency"], consistency_sha)):
        _, actual = u.load_hashed(evidence)
        u.check_pin(actual, expected)

    changes = u.compare(before, b)
    changes["before_manifest_sha256"] = before_digest
    changes["after_manifest_sha256"] = b_sha
    changes["consistency_manifest_sha256"] = consistency_sha
    u.save(paths["changes"], changes)
    return {"status": "stable-comparison-complete", "host": u.host(),
            "counts": changes["counts"], "executable_changed": changes["executable_changed"],
            "outputs": {k: str(v) for k, v in paths.items()}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--prefix", required=True)
    p.add_argument("--expected-host", required=True)
    p.add_argument("--expected-before-sha256", required=True, help="Pinned hash recorded before the patch")
    a = p.parse_args()
    try:
        print(json.dumps(cycle(a.before, a.prefix, a.expected_host, a.expected_before_sha256), indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
