"""Render a verified stored Update Helper cycle as a downstream Markdown report.

This tool reads only the five explicitly selected evidence files. It neither
rescans the game nor infers runtime compatibility from file hashes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

import update_helper as u
import verify_cycle as v


REVIEW = {
    "Executable / library": (
        "Recheck identities used by integrations and run their own compatibility tests."
    ),
    "Asset / data": (
        "Review the listed files and revalidate affected extraction or cached data."
    ),
    "Interface / addon": (
        "Inspect the changed interfaces and run the affected addon's own checks."
    ),
    "Manifest / configuration": (
        "Review installer or configuration differences; these files alone do not establish code changes."
    ),
    "Other": "Identify the file's purpose before assigning downstream work.",
}


def category(path):
    """A routing hint from a path, never a claim about the file's contents."""
    p = PurePosixPath(path.casefold())
    if p.suffix in (".exe", ".dll"):
        return "Executable / library"
    if "assets" in p.parts[:-1] or p.suffix in (".pak", ".dat", ".pck"):
        return "Asset / data"
    if any(part in ("interface", "addons") for part in p.parts[:-1]) or p.suffix in (".lua", ".toc"):
        return "Interface / addon"
    if p.suffix in (".manifest", ".ini", ".cfg", ".xml", ".json", ".yaml", ".yml", ".toml") or (
        p.name.startswith("manifest") and p.suffix == ".txt"
    ):
        return "Manifest / configuration"
    return "Other"


def cell(value):
    """Keep filenames and host labels literal inside Markdown text and tables.

    Evidence is data, including names with Markdown punctuation. Escaping HTML
    and Markdown prevents a path from creating links, headings or table cells.
    Render control characters visibly instead of permitting new report lines.
    """
    visible = "".join(c if c.isprintable() else f"\\u{ord(c):04x}" for c in str(value))
    escaped = html.escape(visible, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#!|])", r"\\\1", escaped)


def _render(documents, verified, paths):
    """Render only documents whose exact bytes have already passed the audit."""
    changes = documents["changes"]
    counts = changes["counts"]
    lines = [
        "# Update Helper verified file-change report",
        "",
        "**Stored evidence verified:** both complete post-capture manifests agree.",
        "",
        "| Added | Removed | Modified | Unchanged |",
        "| ---: | ---: | ---: | ---: |",
        f"| {counts['added']} | {counts['removed']} | {counts['modified']} | {counts['unchanged']} |",
        "",
        "## Capture scope",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Evidence host | {cell(verified['evidence_host'])} |",
        f"| Game installation root | {cell(changes['root'])} |",
        f"| Stored-evidence verifier host | {cell(verified['verification_host'])} |",
        "",
        "All regular files in the recorded installation root were hashed. "
        "Capture is not an atomic filesystem snapshot. This report verifies stored "
        "evidence consistency; it does not establish live game behavior, server "
        "availability, addon compatibility or a publisher's patch date.",
        "",
        "## Recorded captures",
        "",
        "| Capture | Started | Finished | Files | Bytes |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for name in ("before", "after-a", "after-b"):
        doc = documents[name]
        lines.append(
            f"| {name} | {cell(doc['started_utc'])} | {cell(doc['finished_utc'])} "
            f"| {doc['file_count']} | {doc['bytes']:,} |"
        )
    before_sha = changes["before_executable_sha256"]
    after_sha = changes["after_executable_sha256"]
    lines.extend([
        "",
        "## Executable identity",
        "",
        f"**rift_x64.exe content SHA-256: {'unchanged' if before_sha == after_sha else 'changed'}.**",
        "",
        "| Capture | SHA-256 |",
        "| --- | --- |",
        f"| Before | {before_sha} |",
        f"| After | {after_sha} |",
        "",
        "## Downstream review",
        "",
    ])
    if changes["changes"]:
        kinds = Counter(category(change["path"]) for change in changes["changes"])
        lines.extend([
            "Categories are filename-based routing hints. Each maintainer owns "
            "remediation and independent validation; no downstream repositories "
            "were inspected or modified by this report.",
            "",
            "| Category | Changed files | Suggested review |",
            "| --- | ---: | --- |",
        ])
        for name in REVIEW:
            if kinds[name]:
                lines.append(f"| {name} | {kinds[name]} | {REVIEW[name]} |")
    else:
        lines.append(
            "No installation-file differences were observed between the recorded "
            "endpoints. This does not establish that servers did not update or "
            "that downstream runtime behavior is unchanged."
        )
    lines.extend(["", "## Changed files", ""])
    if not changes["changes"]:
        lines.append("None.")
    for change in changes["changes"]:
        left, right = change["before"], change["after"]
        lines.extend([
            f"### {change['kind'].capitalize()}: {cell(change['path'])}",
            "",
            f"Category: {category(change['path'])}.",
            "",
            "| Evidence | Before | After |",
            "| --- | --- | --- |",
        ])
        for label, key in (("Path", "path"), ("Bytes", "size"), ("SHA-256", "sha256")):
            a = "Absent" if left is None else cell(left[key])
            b = "Absent" if right is None else cell(right[key])
            lines.append(f"| {label} | {a} | {b} |")
        lines.append("")
    lines.extend([
        "",
        "## Evidence pins",
        "",
        "The supplied baseline pin was checked before reporting. The verifier "
        "recomputed both comparisons and checked their exact input-file hashes.",
        "",
        "| Evidence | File | SHA-256 |",
        "| --- | --- | --- |",
    ])
    for name, digest in verified["manifest_sha256"].items():
        lines.append(f"| {name} | {cell(paths[name].name)} | {digest} |")
    return "\n".join(lines).rstrip() + "\n"


def render_cycle(before_path, prefix, expected_evidence_host, expected_before_sha256):
    """Audit first, then render the very same bytes, with observable-race checks.

    The audit deliberately remains the authority for acceptance. Its returned
    hashes bind our subsequent reads so a replaced file cannot supply report
    details which were not verified. A final read catches changes during
    rendering; no non-atomic filesystem workflow can promise future immutability.
    """
    verified = v.audit(before_path, prefix, expected_evidence_host, expected_before_sha256)
    paths = {"before": Path(before_path)}
    paths.update({name: u.HERE / f"{prefix}-{name}.json"
                  for name in ("after-a", "after-b", "consistency", "changes")})
    documents = {}
    for name, path in paths.items():
        documents[name], digest = u.load_hashed(path)
        u.check_pin(digest, verified["manifest_sha256"][name])
    text = _render(documents, verified, paths)
    for name, path in paths.items():
        _, digest = u.load_hashed(path)
        u.check_pin(digest, verified["manifest_sha256"][name])
    return text


def output_path(path):
    """Accept only a new ordinary Markdown file directly in the helper root."""
    path = Path(path).absolute()
    if path.parent.resolve(strict=True) != u.HERE:
        raise ValueError("Report output must be a new file in the Update Helper root")
    u.safe_stat(path.parent)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.md", path.name) or u.reserved_component(path.name):
        raise ValueError("Report output must have a safe .md filename")
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"Report output exists; choose a new filename: {path}")
    return path


def save_report(path, text):
    """Publish complete UTF-8 bytes atomically, with no overwrite fallback.

    Match the evidence writer's same-volume hard-link strategy. If another
    process takes the final name after preflight, os.link fails without touching
    its bytes. Temporary files are cleaned up even when publication fails.
    """
    path = output_path(path)
    raw = text.encode("utf-8")
    fd, name = tempfile.mkstemp(prefix=".uh-report-", suffix=".tmp", dir=u.HERE)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.link(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--expected-evidence-host", required=True)
    parser.add_argument("--expected-before-sha256", required=True)
    parser.add_argument("--out", type=Path, help="New .md file in the helper root; otherwise print Markdown")
    args = parser.parse_args(argv)
    try:
        target = output_path(args.out) if args.out else None
        text = render_cycle(args.before, args.prefix, args.expected_evidence_host,
                            args.expected_before_sha256)
        if target is None:
            sys.stdout.write(text)
        else:
            digest = save_report(target, text)
            print(json.dumps({"status": "verified-report-written", "path": str(target),
                              "sha256": digest}, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
