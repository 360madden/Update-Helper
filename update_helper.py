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
import tempfile
import ntpath

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
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("Invalid file record")
        rel = row["path"]
        p = PurePosixPath(rel)
        # Windows aliases, reserved names, alternate streams and control characters
        # are not valid independent evidence paths.
        if (not rel or p.is_absolute() or "\\" in rel or ":" in rel or
                any(x in ("", ".", "..") or ntpath.isreserved(x) for x in rel.split("/"))):
            raise ValueError(f"Invalid relative path: {rel!r}")
        if (type(row.get("size")) is not int or row["size"] < 0 or
                not isinstance(row.get("sha256"), str) or not HEX.fullmatch(row["sha256"])):
            raise ValueError(f"Invalid file evidence: {rel}")
        if type(row.get("mtime_ns")) is not int:
            raise ValueError(f"Invalid timestamp: {rel}")
        key = rel.casefold()
        if key in files:
            raise ValueError(f"Duplicate relative path: {rel}")
        files[key] = row
    if ("rift_x64.exe" not in files or type(doc.get("file_count")) is not int or
            type(doc.get("bytes")) is not int or doc["file_count"] != len(files) or
            doc["bytes"] != sum(x["size"] for x in files.values())):
        raise ValueError("Manifest totals or executable identity invalid")
    return files


def compare(before, after, allow_same_phase=False):
    left, right = validate(before), validate(after)
    if before["host"] != after["host"] or before["root"].casefold() != after["root"].casefold():
        raise ValueError("Host/root mismatch; independent baselines are required")
    if allow_same_phase:
        if before["phase"] != after["phase"]:
            raise ValueError("Consistency check requires the same capture phase")
    elif (before["phase"], after["phase"]) != ("before", "after"):
        raise ValueError("Expected explicit before and after manifests")
    if dt.datetime.fromisoformat(after["started_utc"]) < dt.datetime.fromisoformat(before["finished_utc"]):
        raise ValueError("Captures overlap or are out of order")
    counts = dict(added=0, removed=0, modified=0, unchanged=0)
    changes = []
    for k in sorted(left.keys() | right.keys()):
        a, b = left.get(k), right.get(k)
        kind = ("added" if a is None else "removed" if b is None else
                "unchanged" if (a["sha256"], a["size"], a["path"]) == (b["sha256"], b["size"], b["path"]) else "modified")
        counts[kind] += 1
        if kind != "unchanged":
            changes.append({"kind": kind, "path": (b or a)["path"], "before": a, "after": b})
    # Include both executable identities even for an unchanged installation.
    # Downstream consumers should not have to infer their build from a change list.
    return {"schema": "update-helper.comparison.v1", "host": before["host"],
            "root": before["root"], "before_utc": before["finished_utc"],
            "after_utc": after["finished_utc"], "counts": counts,
            "before_executable_sha256": left["rift_x64.exe"]["sha256"],
            "after_executable_sha256": right["rift_x64.exe"]["sha256"],
            "before_file_count": before["file_count"], "after_file_count": after["file_count"],
            "before_bytes": before["bytes"], "after_bytes": after["bytes"],
            "executable_changed": any(c["path"].casefold() == "rift_x64.exe" for c in changes),
            "changes": changes}


def output_path(path):
    """Restrict outputs to ordinary JSON filenames directly in this checkout."""
    path = Path(path).absolute()
    if path.parent.resolve(strict=True) != HERE:
        raise ValueError("Output must be a new file in the Update Helper root")
    safe_stat(path.parent)
    # On Windows a colon can create an alternate stream; reserved names can
    # refer to devices. Whitelist ordinary filenames before touching the disk.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.json", path.name) or ntpath.isreserved(path.name):
        raise ValueError("Output must have a safe .json filename")
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Output exists; choose a new filename: {path}")
    return path


def save(path, obj):
    """Flush complete bytes to a temporary file, then publish without replacement.

    A hard link on the same NTFS volume atomically creates the final name only
    if absent. Unlike opening the final file with 'x', readers cannot observe
    an incomplete JSON document. If linking is unavailable, fail closed.
    """
    path = output_path(path)
    raw = (json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    fd, name = tempfile.mkstemp(prefix=".uh-", suffix=".tmp", dir=HERE)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return hashlib.sha256(raw).hexdigest()


def unique_keys(pairs):
    """Reject duplicate JSON fields instead of silently keeping the last."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_hashed(path):
    """Parse and hash the exact same bytes; reject observable concurrent edits."""
    path = Path(path)
    st = safe_stat(path)
    if not stat.S_ISREG(st.st_mode):
        raise ValueError(f"Not a regular manifest: {path}")
    expected = stamp(st)
    stable_handle = handle_stamp(st)
    with path.open("rb") as f:
        if handle_stamp(os.fstat(f.fileno())) != stable_handle:
            raise ValueError(f"Manifest changed while opening: {path}")
        raw = f.read()
        if handle_stamp(os.fstat(f.fileno())) != stable_handle:
            raise ValueError(f"Manifest changed while reading: {path}")
    if stamp(safe_stat(path)) != expected or len(raw) != st.st_size:
        raise ValueError(f"Manifest changed during read: {path}")
    obj = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_keys)
    return obj, hashlib.sha256(raw).hexdigest()


def load(path):
    return load_hashed(path)[0]


def check_pin(actual, expected):
    if expected is not None:
        if not isinstance(expected, str) or not HEX.fullmatch(expected):
            raise ValueError("Expected SHA-256 must be 64 lowercase hexadecimal characters")
        if actual != expected:
            raise ValueError(f"Manifest SHA-256 mismatch: expected {expected}, got {actual}")


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
    comp.add_argument("--expected-before-sha256", help="Independently recorded before-manifest hash")
    comp.add_argument("--expected-after-sha256", help="Independently recorded after-manifest hash")
    chk = commands.add_parser("verify")
    chk.add_argument("manifest", type=Path)
    chk.add_argument("--expected-sha256", help="Verify a previously recorded manifest hash")
    args = parser.parse_args()
    try:
        if args.cmd in ("capture", "compare"):
            output_path(args.out)
        if args.cmd == "capture":
            if HERE.is_relative_to(args.game_dir.resolve(strict=True)):
                raise ValueError("Output repository cannot be inside scanned source")
            obj = capture(args.game_dir, args.phase, args.expected_host)
            save(args.out, obj)
            result = {k: obj[k] for k in ("phase", "host", "file_count", "bytes", "complete")}
            result["exe_sha256"] = validate(obj)["rift_x64.exe"]["sha256"]
        elif args.cmd == "compare":
            before, before_sha = load_hashed(args.before)
            after, after_sha = load_hashed(args.after)
            check_pin(before_sha, args.expected_before_sha256)
            check_pin(after_sha, args.expected_after_sha256)
            obj = compare(before, after, args.consistency)
            obj["before_manifest_sha256"] = before_sha
            obj["after_manifest_sha256"] = after_sha
            save(args.out, obj)
            result = {"counts": obj["counts"], "executable_changed": obj["executable_changed"]}
        else:
            obj, manifest_sha = load_hashed(args.manifest)
            check_pin(manifest_sha, args.expected_sha256)
            files = validate(obj)
            result = {"valid": True, "host": obj["host"], "phase": obj["phase"],
                      "file_count": len(files), "bytes": obj["bytes"],
                      "exe_sha256": files["rift_x64.exe"]["sha256"],
                      "manifest_sha256": manifest_sha}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
