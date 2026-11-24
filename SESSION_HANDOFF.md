# SESSION HANDOFF — November 24, 2026 patch contingency

## Host and provenance
- Active machine: **LEGION** (verified by machine name, not inferred).
- Repo: `C:\work\Update Helper`, independent reconstructed checkout. Original AMD-DESKTOP checkout unavailable for about two months; do not claim its history was recovered. GitHub owner listing found no existing Update Helper repository.
- Possible Tuesday patch: November 24, 2026; no publisher confirmation or post-patch result asserted.

## Immutable pre-patch evidence
- `before-20261124-legion.json`: 266/266 regular game files SHA-256 hashed, 26,754,214,661 bytes, complete. Captured UTC 2026-11-24 04:46:13.721618–04:47:24.724674 (Nov 23 EST).
- Manifest SHA-256: `6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e`.
- Game root: `C:\Program Files (x86)\Glyph\Games\RIFT\Live`.
- Executable SHA-256: `df954b798331e18359be62a31cc74b49fc3f50b87385ebb080a5448256322c01`.
- Verified preserved executable (60,574,536 bytes): `.local\prepatch\df954b798331e18359be62a31cc74b49fc3f50b87385ebb080a5448256322c01\rift_x64.exe`. Local only; not part of Git. Do not execute or substitute into game installation.
- `workbridge-before-20261124-legion.json`: earlier read-only supplemental capture, 981 game/addon inventory entries, 732 SHA-256 entries, 0 reported errors. Manifest SHA-256 `b425f9fa328f38e84e4e6c53f05f07cfdc08136e23056ba43a8a2e05ed89b0c4`. Independent comparison: all 266 game paths and file sizes matched; all 17 overlapping game content hashes matched. Metadata-only entries are not content evidence.
- `repo-inventory-20261124-legion.json`: 31 top-level Git directories (includes rehearsal/validation clones and Update Helper while still unborn), SHA-256 `8e7b61f89b03306a3d31987af1fcd1d9c45acb81a4d9ad8201fd42eef38b2ead`. All inventories are time-specific.
- RIFT running at initial preflight, but no observed concurrent changes during the successful full capture. No game processes or files modified by this helper.

## Next action after Glyph finishes
From PowerShell on LEGION:

```powershell
Set-Location -LiteralPath 'C:\work\Update Helper'
python -B -m unittest -v test_update_helper test_post_patch test_verify_cycle
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
python -B update_helper.py verify before-20261124-legion.json --expected-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e
if ($LASTEXITCODE -ne 0) { throw 'Baseline invalid' }
python -B post_patch.py --expected-host LEGION --before before-20261124-legion.json --expected-before-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e --prefix patch-20261124-attempt-01
if ($LASTEXITCODE -ne 0) { throw 'Capture or comparison failed; preserve evidence and investigate' }
python -B verify_cycle.py --before before-20261124-legion.json --prefix patch-20261124-attempt-01 --expected-evidence-host LEGION --expected-before-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e
if ($LASTEXITCODE -ne 0) { throw 'Stored evidence verification failed; do not distribute' }
```

The cycle creates two complete after manifests, a consistency report and, only if stable, a changes report. Use a fresh attempt prefix on retry. Compare file content, not merely timestamps. If no file content changed, report no observed installation-file change, not a claim that servers did not update.

## Downstream routing (read-only evidence only)
- First inventory actual top-level repositories again, avoiding modification of all downstream worktrees. Preserve existing dirty changes.
- Executable/library changes: provide confirmed build identity and file-level change report to affected repo sessions for independent compatibility testing.
- Asset/data changes: provide changed archive paths and hashes to relevant asset/data consumers, such as RiftWorld.
- Interface/addon changes: provide file evidence to addon maintainers (RiftChatModern, LuaPadModern and other applicable repositories); they validate their own code.
- Workbridge: review its own update inventory and capabilities as necessary. Do not reset/reload game, change client files, or mass-edit code.
- Exclude rehearsal clones from default recovery targets unless a maintainer specifically selects them. `telarafly` is a protected reference, never modified. Star_Wrath_RE concerns another game and is not a RIFT patch target.
- Do not assume old AMD-DESKTOP inventory matches LEGION. RR2 and RPT had existing dirty files at preflight; avoid overwriting or staging them. RIFT_Memory_Mover had an unborn history.
- Preserve the evidence and local Git history. Reconcile original history explicitly when AMD-DESKTOP returns.

## Reliability hardening
- Use the pinned baseline SHA-256 in the command above. Do not calculate a replacement pin from an untrusted or edited baseline.
- Atomic no-overwrite publication; parse and hash identical bytes; reject ambiguous JSON fields and unsafe Windows filenames. Revalidate the three input manifests before final comparison publication.

### Reliability audit checkpoint
- Original commit `914028074808f9f01b4bdcf942156a29d72ddc07` preserves the first validated implementation and original evidence. Original evidence files remain byte-for-byte unchanged and match their committed Git blobs.
- Expanded regression suite initially found a Windows drive-relative path validation defect (`a:stream`). Explicitly rejecting colons corrected it. On 2026-11-24 at 05:11 UTC, the complete 26-test suite passed on LEGION (exit 0).
- Pinned verification of the real 266-file baseline passed; an intentionally wrong post-patch pin returned exit 2 before capture. Git diff check passed.
- Do not regenerate the pre-patch baseline after the updater runs.

### Independent evidence verification
- Validated hardening checkpoint committed as `4535f48d0ab09bbd7296e0331f7742ac08933b9d`.
- `verify_cycle.py` independently recomputes both reports and binds all five files to their exact bytes and the trusted baseline pin; no game scan or source changes. It rejects incomplete bundles, altered snapshots/reports, incorrect pins, host/phase mismatches and ambiguous numeric types.
- On 2026-11-24 at 05:12 UTC, all 35 regression tests passed on LEGION (exit 0), including nine independent-verifier cases. No real post-patch capture has been performed by this test suite.
