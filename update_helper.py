"""Update Helper: host-bound, read-only file evidence for RIFT patch recovery.

Standard library only. No game launch, process interaction, or source writes.
Snapshots are deliberately immutable; failed captures cannot be compared.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import stat
import sys

SCHEMA = "update-helper.game-files.v1"
HERE = Path(__file__).resolve().parent
DEFAULT_GAME = Path(r"C:\Program Files (x86)\Glyph\Games\RIFT\Live")
HEX = re.compile(r"[0-9a-f]{64}\Z")


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def host():
    return socket.gethostname().upper()


def safe_stat(path):
    """Refuse symlinks and Windows reparse points instead of following them."""
    s = path.lstat()
    if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"Reparse point or symlink refused: {path}")
    return s


def stamp(s):
    return (s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_ino, s.st_dev)


def handle_stamp(s):
    """Windows handle ctime can differ from path ctime for an unchanged file."""
    return (s.st_size, s.st_mtime_ns, s.st_ino, s.st_dev)


def inventory(root):
    """Collect every regular file, with deterministic case-insensitive keys."""
    found = {}
    def visit(directory):
        for p in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
            s = safe_stat(p)
            if stat.S_ISDIR(s.st_mode):
                visit(p)
            elif stat.S_ISREG(s.st_mode):
                rel = p.relative_to(root).as_posix()
                key = rel.casefold()
                if key in found:
                    raise ValueError(f"Case-insensitive collision: {rel}")
                found[key] = (rel, stamp(s))
            else:
                raise ValueError(f"Not a regular file: {p}")
    visit(root)
    return found


def digest(path, expected):
    """Check metadata before, during and after hashing to reject obvious races."""
    if stamp(safe_stat(path)) != expected:
        raise ValueError(f"Changed before hashing: {path}")
    with path.open("rb") as f:
        if handle_stamp(os.fstat(f.fileno())) != (expected[0], expected[1], expected[3], expected[4]):
            raise ValueError(f"Changed while opening: {path}")
        sha = hashlib.file_digest(f, "sha256").hexdigest()
        if handle_stamp(os.fstat(f.fileno())) != (expected[0], expected[1], expected[3], expected[4]):
            raise ValueError(f"Changed during hashing: {path}")
    if stamp(safe_stat(path)) != expected:
        raise ValueError(f"Changed after hashing: {path}")
    return sha


def capture(root, phase, expected_host):
    if host() != expected_host.upper():
        raise ValueError(f"Wrong host: expected {expected_host}, got {host()}")
    root = Path(root).absolute()
    for part in reversed([root, *root.parents]):
        safe_stat(part)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Game root must be a directory")
    start = utc()
    before = inventory(root)
    if "rift_x64.exe" not in before:
        raise ValueError("Missing rift_x64.exe; refusing to identify this as a RIFT install")
    records = []
    for i, (key, (rel, info)) in enumerate(sorted(before.items()), 1):
        sha = digest(root / rel, info)
        records.append({"path": rel, "size": info[0], "mtime_ns": info[1], "sha256": sha})
        if i % 25 == 0:
            print(f"Hashed {i}/{len(before)} files", file=sys.stderr, flush=True)
    if before != inventory(root):
        raise ValueError("Directory changed during capture; retry after updater settles")
    result = {"schema": SCHEMA, "phase": phase, "host": host(), "root": str(root),
              "started_utc": start, "finished_utc": utc(), "complete": True,
              "files": records, "file_count": len(records),
              "bytes": sum(r["size"] for r in records)}
    validate(result)
    return result


def validate(doc):
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or doc.get("complete") is not True:
        raise ValueError("Unsupported or incomplete manifest")
    if doc.get("phase") not in ("before", "after"):
        raise ValueError("Invalid phase")
    for k in ("host", "root", "started_utc", "finished_utc"):
        if not isinstance(doc.get(k), str) or not doc[k]:
            raise ValueError(f"Missing {k}")
    for k in ("started_utc", "finished_utc"):
        if dt.datetime.fromisoformat(doc[k]).tzinfo is None:
            raise ValueError("Timestamp must include timezone")
    if dt.datetime.fromisoformat(doc["finished_utc"]) < dt.datetime.fromisoformat(doc["started_utc"]):
        raise ValueError("Invalid timestamp order")
    if not isinstance(doc.get("files"), list):
        raise ValueError("Missing file list")
    files = {}
    for row in doc["files"]:
        rel = row["path"]
        p = PurePosixPath(rel)
        if not rel or p.is_absolute() or any(x in ("", ".", "..") for x in rel.split("/")) or "\\" in rel or ":" in rel:
            raise ValueError(f"Invalid relative path: {rel}")
        if type(row["size"]) is not int or row["size"] < 0 or not HEX.fullmatch(row["sha256"]):
            raise ValueError(f"Invalid file evidence: {rel}")
        if type(row["mtime_ns"]) is not int:
            raise ValueError(f"Invalid timestamp: {rel}")
        key = rel.casefold()
        if key in files:
            raise ValueError(f"Duplicate relative path: {rel}")
        files[key] = row
    if "rift_x64.exe" not in files or doc.get("file_count") != len(files) or doc.get("bytes") != sum(x["size"] for x in files.values()):
        raise ValueError("Manifest totals or executable identity invalid")
    return files


def compare(before, after, allow_same_phase=False):
    left, right = validate(before), validate(after)
    if before["host"] != after["host"] or before["root"].casefold() != after["root"].casefold():
        raise ValueError("Host/root mismatch; independent baselines are required")
    if not allow_same_phase and (before["phase"], after["phase"]) != ("before", "after"):
        raise ValueError("Expected explicit before and after manifests")
    if dt.datetime.fromisoformat(after["started_utc"]) < dt.datetime.fromisoformat(before["finished_utc"]):
        raise ValueError("Captures overlap or are out of order")
    counts = dict(added=0, removed=0, modified=0, unchanged=0)
    changes = []
    for k in sorted(left.keys() | right.keys()):
        a, b = left.get(k), right.get(k)
        kind = ("added" if a is None else "removed" if b is None else
                "unchanged" if (a["sha256"], a["size"]) == (b["sha256"], b["size"]) else "modified")
        counts[kind] += 1
        if kind != "unchanged":
            changes.append({"kind": kind, "path": (b or a)["path"], "before": a, "after": b})
    return {"schema": "update-helper.comparison.v1", "host": before["host"],
            "root": before["root"], "before_utc": before["finished_utc"],
            "after_utc": after["finished_utc"], "counts": counts,
            "executable_changed": any(c["path"].casefold() == "rift_x64.exe" for c in changes),
            "changes": changes}


def save(path, obj):
    path = Path(path).absolute()
    # Exclusive creation prevents accidentally replacing the last good baseline.
    # Publish only complete serialized JSON; a truncated write is rejected by load/validate.
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    # Output is confined to this repository, not the scanned game tree.
    if path.parent.resolve(strict=True) != HERE:
        raise ValueError("Output must be a new file in the Update Helper root")
    safe_stat(path.parent)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="cmd", required=True)
    cap = commands.add_parser("capture")
    cap.add_argument("--phase", choices=["before", "after"], required=True)
    cap.add_argument("--expected-host", required=True)
    cap.add_argument("--game-dir", type=Path, default=DEFAULT_GAME)
    cap.add_argument("--out", type=Path, required=True)
    comp = commands.add_parser("compare")
    comp.add_argument("--before", type=Path, required=True)
    comp.add_argument("--after", type=Path, required=True)
    comp.add_argument("--out", type=Path, required=True)
    comp.add_argument("--consistency", action="store_true", help="Compare repeated same-phase captures")
    chk = commands.add_parser("verify")
    chk.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        if args.cmd in ("capture", "compare"):
            if args.out.absolute().parent.resolve(strict=True) != HERE:
                raise ValueError("Output must be a new file in the Update Helper root")
            if args.out.exists():
                raise ValueError("Output exists; choose a new filename")
        if args.cmd == "capture":
            if HERE.is_relative_to(args.game_dir.resolve(strict=True)):
                raise ValueError("Output repository cannot be inside scanned source")
            obj = capture(args.game_dir, args.phase, args.expected_host)
            save(args.out, obj)
            result = {k: obj[k] for k in ("phase", "host", "file_count", "bytes", "complete")}
            result["exe_sha256"] = validate(obj)["rift_x64.exe"]["sha256"]
        elif args.cmd == "compare":
            before, after = load(args.before), load(args.after)
            if args.consistency and before["phase"] != after["phase"]:
                raise ValueError("Consistency check requires the same capture phase")
            obj = compare(before, after, args.consistency)
            obj["before_manifest_sha256"] = hashlib.sha256(args.before.read_bytes()).hexdigest()
            obj["after_manifest_sha256"] = hashlib.sha256(args.after.read_bytes()).hexdigest()
            save(args.out, obj)
            result = {"counts": obj["counts"], "executable_changed": obj["executable_changed"]}
        else:
            obj = load(args.manifest)
            files = validate(obj)
            result = {"valid": True, "host": obj["host"], "phase": obj["phase"],
                      "file_count": len(files), "bytes": obj["bytes"],
                      "exe_sha256": files["rift_x64.exe"]["sha256"],
                      "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest()}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
