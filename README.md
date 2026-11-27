# Update Helper — LEGION recovery workspace

**Mission:** produce trustworthy, reusable file-change evidence for RIFT patch recovery across all present and future repositories in `C:\work`. Downstream projects own their own code changes and validation.

## Provenance

Reconstructed on LEGION on November 23–24, 2026, because the original AMD-DESKTOP checkout is unavailable for approximately two months and no corresponding repository was found in the connected GitHub account. This is a new local history, **not** a clone or restoration of the original commits. Do not overwrite or pretend to merge the original history when it becomes available. Reconcile provenance explicitly. No game files are modified.

## Quick start (PowerShell, LEGION)

```powershell
Set-Location -LiteralPath 'C:\work\Update Helper'
python -B -m unittest discover -v
python -B update_helper.py verify before-20261124-legion.json --expected-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e
```

After the game updater has fully completed and files have settled, the recommended one-command workflow is:

```powershell
python -B post_patch.py --expected-host LEGION --before before-20261124-legion.json --expected-before-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e --prefix patch-20261124-attempt-01
```

This captures the installation twice, compares the two post-patch states and publishes a final changes report only if the states match. Each retry must use a new prefix.

The example prefix above is a filename, not an asserted patch date. Choose a new dated prefix for each actual run. Both post-captures must also follow the baseline chronologically; a clock rollback cannot produce a successful final report.

### Independently verify the completed evidence bundle

```powershell
python -B verify_cycle.py --before before-20261124-legion.json --prefix patch-20261124-attempt-01 --expected-evidence-host LEGION --expected-before-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e
```

Run this before distributing a completed comparison to downstream repositories. The verifier re-parses all five JSON inputs, checks the pre-patch pin, verifies both post-capture phases and host identity, recomputes both reports, and checks their byte-level provenance. It only reads stored evidence and does not scan the game. A successful result confirms stored evidence consistency, not live client behavior or independently authenticated game-file contents.

### Generate a verified downstream report

```powershell
python -B report_cycle.py --before before-20261124-legion.json --prefix patch-20261124-attempt-01 --expected-evidence-host LEGION --expected-before-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e --out patch-20261124-attempt-01-summary.md
```

Use the prefix of the completed cycle you selected. Omit `--out` to print Markdown. A saved report must be a new `.md` file in the helper root; existing files are never overwritten. Reporting independently verifies the entire bundle before rendering, then binds every detail to those verified bytes. It includes capture scope and times, file counts, executable identities, changed paths with before/after hashes, and all evidence pins. Filename-based categories suggest downstream review without claiming compatibility or modifying another repository.

For a manual, step-by-step comparison, use new names for every attempt (the independent bundle verifier expects the four output names and provenance produced by post_patch.py):

```powershell
python -B update_helper.py capture --phase after --expected-host LEGION --out after-20261124-legion-a.json
python -B update_helper.py capture --phase after --expected-host LEGION --out after-20261124-legion-b.json
python -B update_helper.py compare --consistency --before after-20261124-legion-a.json --after after-20261124-legion-b.json --out consistency-20261124-legion.json
python -B update_helper.py compare --before before-20261124-legion.json --expected-before-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e --after after-20261124-legion-b.json --out changes-20261124-legion.json
```

Check each exit code before continuing. A successful compare may report changed files; change itself is not a failure. Exit 2 means invalid evidence, wrong host, inaccessible files, or another error. Never substitute incomplete evidence. If a repeated post-patch comparison differs, investigate and repeat before distributing results.

## Evidence design

- Every regular file in the explicit game installation root receives a SHA-256 hash; no extension or file-size exclusions.
- Capture records host, canonical source root, UTC timestamps, relative paths, sizes and hashes. A second directory inventory and per-file metadata checks detect observable concurrent modifications. This is not an atomic filesystem snapshot.
- Refuse symlinks/reparse points, inaccessible files, case collisions, missing game executable, mismatched host/root, invalid schemas and overlapping captures.
- New ordinary JSON output files only, confined to this repository root. Complete flushed bytes are published atomically using a same-volume hard link; no existing file can be overwritten. A failed publication leaves no final manifest. The post-patch runner requires an independently recorded baseline SHA-256 and checks the saved after manifests before publishing results. Git preserves JSON bytes without line-ending conversion.
- Preserve immutable before/after manifests and comparison JSON. Comparison JSON includes both executable identities, file counts and byte totals even if nothing changed. The one-command cycle binds the consistency report hash as well. File hashes alone do not establish live behavior, addon compatibility, or successful runtime validation.
- Python 3.11 or newer and its standard library are sufficient; no Python packages are required. Windows filename checks are applied consistently even when stored evidence is verified on Linux.

## Continuous verification

GitHub Actions runs all discovered regression tests on Windows and Linux with Python 3.11 and 3.14. Every matrix job also verifies the pinned baseline, the committed rehearsal bundle and the November 28 capture bundle, then checks that tracked files were not rewritten. These checks use disposable synthetic installations and stored evidence; they require no RIFT installation, LEGION connection or application service. Cloud runners are development scaffolding; capture, comparison and reporting remain standalone local commands.

## Inventory the actual repository candidates

```powershell
python -B inventory_repos.py --root C:\work --expected-host LEGION --out repo-inventory-YYYYMMDD-legion-01.json
```

Replace the date placeholder with the current date and select a fresh filename. This discovers immediate child directories with `.git` markers and reads bounded HEAD/branch metadata for ordinary repositories. It does not recurse through source trees, fetch remotes, run worktree-status scans, or modify downstream files. `telarafly` is explicitly marked as a read-only reference. Presence alone does not mean a repository consumes RIFT.

Gitfile targets and linked/reparse entries are recorded without following them. Unavailable or invalid metadata remains unknown; `clean` and `changed_entries` are always unknown because this inventory deliberately does not scan worktree status. A partial inventory is preserved for review and the command returns exit 2. Inspect its per-entry errors and scope before using it to route work; do not reinterpret partial discovery as an empty or clean workspace.

## Existing complementary tools

- `C:\work\workbridge-mcp\scripts\Rift-Update-Helper.ps1`: selected code hashes plus asset metadata and addon inventory. Do not treat metadata-only matches as full content verification.
- `C:\work\riftreader2\tools\RiftUpdateAnalyzer`: selected file and route evidence; follow that repo's own README.
- `C:\work\rre\tools\Run-RiftUpdateAnalyzer.ps1`: existing offline executable comparison tooling; use only for authorized, appropriate file comparison and each repo's own workflow.

## Patch recovery policy

Keep Update Helper read-only toward the game, installed addons and all downstream repos. Discover the actual local repository inventory on each patch cycle; classify observed changes and route evidence to maintainers. Do not mass-edit, reset, pull, deploy or claim downstream compatibility merely because the game files were captured. Never modify the preserved `C:\work\telarafly` reference repository. Keep separate machine-bound baselines and mark absent repos explicitly. Patch date is a planning assumption, not a confirmed publisher announcement.

See SESSION_HANDOFF.md for current execution state.
