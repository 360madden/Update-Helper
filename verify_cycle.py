"""Independently verify a completed Update Helper evidence bundle.

Read-only: this checks stored JSON files, not the game installation. It
recomputes the comparisons instead of trusting the saved change counts.
"""
import argparse
import json
from pathlib import Path
import re
import sys

import update_helper as u


def canonical(obj):
    """Compare JSON values exactly, ignoring object key order, not value types."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def require_equal(actual, expected, label):
    if canonical(actual) != canonical(expected):
        raise ValueError(f"{label} does not match independently recomputed evidence")


def audit(before_path, prefix, expected_evidence_host, expected_before_sha256):
    """Verify a complete, stable cycle against the separately recorded baseline pin."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", prefix):
        raise ValueError("Invalid cycle prefix")
    if expected_before_sha256 is None:
        raise ValueError("Pinned baseline SHA-256 is required")

    # Explicit filenames only: never silently select a newer or partial attempt.
    paths = {"before": Path(before_path)}
    paths.update({name: u.HERE / (prefix + "-" + name + ".json")
                  for name in ("after-a", "after-b", "consistency", "changes")})
    documents = {}
    hashes = {}
    for name, path in paths.items():
        documents[name], hashes[name] = u.load_hashed(path)
    u.check_pin(hashes["before"], expected_before_sha256)

    before = documents["before"]
    a, b = documents["after-a"], documents["after-b"]
    for name, doc, phase in (("before", before, "before"),
                             ("after-a", a, "after"), ("after-b", b, "after")):
        u.validate(doc)
        if doc["host"] != expected_evidence_host.upper() or doc["phase"] != phase:
            raise ValueError(f"{name}: host or phase mismatch")

    # Recompute the post-capture agreement from original snapshots; a saved
    # zero-change count is not itself proof that the two captures agreed.
    agreement = u.compare(a, b, allow_same_phase=True)
    agreement["before_manifest_sha256"] = hashes["after-a"]
    agreement["after_manifest_sha256"] = hashes["after-b"]
    require_equal(documents["consistency"], agreement, "Consistency report")
    if any(agreement["counts"][kind] for kind in ("added", "removed", "modified")):
        raise ValueError("Post-patch captures are not stable")

    # Both after captures must have started after the baseline completed.
    # The first comparison is also a chronological and scope check.
    u.compare(before, a)
    changes = u.compare(before, b)
    changes["before_manifest_sha256"] = hashes["before"]
    changes["after_manifest_sha256"] = hashes["after-b"]
    changes["consistency_manifest_sha256"] = hashes["consistency"]
    require_equal(documents["changes"], changes, "Changes report")

    # Detect observable changes to any of the files during verification.
    for name, path in paths.items():
        _, actual = u.load_hashed(path)
        u.check_pin(actual, hashes[name])

    return {
        "status": "verified-stored-evidence",
        "evidence_host": before["host"],
        "verification_host": u.host(),
        "counts": changes["counts"],
        "before_executable_sha256": changes["before_executable_sha256"],
        "after_executable_sha256": changes["after_executable_sha256"],
        "manifest_sha256": hashes,
        "scope": "stored evidence consistency only; not a live game verification"
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--expected-evidence-host", required=True)
    parser.add_argument("--expected-before-sha256", required=True)
    args = parser.parse_args()
    try:
        result = audit(args.before, args.prefix, args.expected_evidence_host,
                       args.expected_before_sha256)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
