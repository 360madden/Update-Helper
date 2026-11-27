# SESSION HANDOFF — November 28, 2026 (Asia/Manila)

## Current outcome

- Active physical machine: **LEGION**, independently verified with `hostname.exe`. Python is 3.14.10. The Linux development checkout uses Python 3.12.14; it is scaffolding, not an application dependency.
- Repository: `C:\work\Update Helper`; public remote: https://github.com/360madden/Update-Helper; branch `main`. The recovered starting revision for this session was `6267658902a9d7cdd20f53244fd6805d3f26da07`. Use Git history and the Actions run for the current revision when resuming.
- Two fresh complete installation captures ran on **November 28, 2026, 06:29:09–06:31:16 Manila** (November 27, 22:29:09–22:31:16 UTC). Each hashed **266 files / 26,754,214,661 bytes**. Both captures agree, and both agree with the pinned November 24 baseline: **0 added, 0 removed, 0 modified, 266 unchanged**.
- `verify_cycle.py` independently verified the five-file bundle. This is evidence about installation files, not server updates, login availability, live gameplay or downstream compatibility. No publisher patch date is asserted.
- Human report: `patch-20261128-legion-01-summary.md`. It was generated on LEGION only after independent verification.

## Durable scope and provenance

Update Helper records file-change evidence for current and future consumers under `C:\work`. Downstream maintainers own their changes and runtime tests. Never modify game files, installed addons or another repository from this helper; never interact with game processes. `C:\work\telarafly` remains a protected read-only reference. Star_Wrath_RE is not a RIFT patch target merely because it appears in the inventory.

LEGION is an independent reconstructed Git history, not a restoration of AMD-DESKTOP's original checkout. AMD-DESKTOP remains unavailable for approximately two months. Preserve both histories and reconcile explicitly when it returns. The user previously authorized commit/push using `360madden <360madden@gmail.com>` and public publication of this project.

## Immutable evidence pins

Game installation root: `C:\Program Files (x86)\Glyph\Games\RIFT\Live`.

| Evidence file | SHA-256 |
| --- | --- |
| `before-20261124-legion.json` | `6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e` |
| `patch-20261128-legion-01-after-a.json` | `82e6742c1080df5513f3e55644a55ad488617e8421c29d8806c8ce12cab7effe` |
| `patch-20261128-legion-01-after-b.json` | `441c78ef438103a4dec72ab9c5df00cc266153331cc16d7c3a726c195db5398b` |
| `patch-20261128-legion-01-consistency.json` | `0bacebdf637869e772b1afe6eee22d80a7431b04ee8849225d808614260c8a87` |
| `patch-20261128-legion-01-changes.json` | `6605cec6311d987151b425313fc8d91fe63c7658c936104fc175f3bf3a66b433` |
| `patch-20261128-legion-01-summary.md` | `c165ab5a1e5c29a26441d8028603a80c3d9f38d56429207eb857243af36f61d4` |
| `repo-inventory-20261128-legion-01.json` | `adda5457ea0ce648e5e6ce1101d08dcd249db6a679018f1a41bbe47cb589ec06` |

Before and after executable SHA-256: `df954b798331e18359be62a31cc74b49fc3f50b87385ebb080a5448256322c01`. The baseline completed at `2026-11-24T04:47:24.724674+00:00`. Never regenerate or repin it after an update.

The earlier handoff recorded a local-only preserved 60,574,536-byte executable at `.local\prepatch\df954b798331e18359be62a31cc74b49fc3f50b87385ebb080a5448256322c01\rift_x64.exe`. That copy was not reverified this session; never execute it, substitute it into the installation or commit raw game binaries.

## Implementation checkpoint

- Replaced Python-3.13-only `ntpath.isreserved` calls with deterministic Windows filename-component validation. Before the fix the original suite had 30 errors on cloud Python 3.12. The helper now supports Python 3.11+ with the standard library.
- Reproduced and fixed a clock-rollback acceptance bug: the cycle runner now verifies that the first after-capture also follows the baseline. It cannot publish a successful final report that the independent verifier rejects for that chronology error.
- Added `report_cycle.py`: verify an explicit bundle, bind report details to the audited byte hashes, show scope/times/counts/full changed-file hashes and conservative routing hints, and atomically publish a new Markdown file. JSON and Markdown are stored without Git newline conversion.
- Added `inventory_repos.py`: shallow explicit-root discovery, bounded read-only Git HEAD/branch observations, unknown cleanliness, no linked-target traversal, preserved partial results and a protected-reference flag.
- Added GitHub Actions for Windows/Linux × Python 3.11/3.14: all discovered regression tests, original baseline pin, committed rehearsal bundle, current captured bundle, and a tracked-file immutability check. No Python package installation or application service dependency. Inspect the hosted run for the exact current commit rather than assuming configuration means a pass.
- Review reproduced a test-fixture isolation defect under inherited Git routing. The fixture now isolates environment/config/hooks/templates/signing, with a regression preserving a dirty decoy repository. The final **57/57 tests passed on cloud Linux/Python 3.12.14 and physical LEGION/Python 3.14.10**. LEGION completed the final suite at `2026-11-27T22:39:56.871Z` (November 28, 06:39:56 Manila), exit 0. Independent review also repeated the decoy-repository reproduction successfully. Hosted results must be read from Actions for the exact commit.

## Repository inventory and preserved existing work

The current inventory found **34 immediate-child Git candidates**: **18 with complete revision metadata**, **15 Gitfile candidates whose targets were deliberately not followed**, and **1 unborn/unresolved HEAD** (`Rift_Memory_Mover`, branch `master`). It contains no skipped directory entries. `complete: false` and exit 2 accurately preserve those limits; they are not a reason to change or repair other repositories. Worktree cleanliness was not inspected for any candidate.

Ten evidence files from other sessions were already untracked on arrival. Preserve them, do not mass-stage/delete them:

- `riftworld-20261126-01-{after-a,after-b,changes,consistency}.json`
- `taxi-20261124-current-01-{after-a,after-b,changes,consistency}.json`
- `rr2-patch-20261126-01-recheck-{changes,consistency}.json`

The complete RiftWorld and Taxi bundles were independently verified against the original pin this session; both show 266 unchanged files. The two RR2 recheck files are comparison-only outputs, not a complete capture bundle. The committed `rr2-rehearsal-20261124-01` bundle also verifies with 266 unchanged files. Do not confuse any older rehearsal with today's actual captures.

## Resume commands (PowerShell on LEGION)

```powershell
Set-Location -LiteralPath 'C:\work\Update Helper'
python -B -m unittest discover -v
if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed' }
python -B verify_cycle.py --before before-20261124-legion.json --prefix patch-20261128-legion-01 --expected-evidence-host LEGION --expected-before-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e
if ($LASTEXITCODE -ne 0) { throw 'Stored evidence verification failed' }
python -B report_cycle.py --before before-20261124-legion.json --prefix patch-20261128-legion-01 --expected-evidence-host LEGION --expected-before-sha256 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e
```

The last command prints verified Markdown; the saved summary already exists and must not be overwritten. Current stored evidence can be checked offline on another machine by using `--expected-evidence-host LEGION`. Capture/inventory execution must remain bound to the actual intended machine.

## Next practical work

1. Inspect the latest GitHub CI result and preserve any newer local work before editing. Revisit a failure only with new evidence; do not repeatedly rescan unchanged game files for status alone.
2. Before a newly observed installation update, preserve an explicitly selected and independently pinned baseline. After the updater has finished, use a fresh prefix, two full captures, independent verification and a new downstream report. Never select the newest baseline implicitly.
3. The remaining useful backlog is bounded preflight diagnostics (source accessibility, baseline identity and output publication capability) and an explicit historical evidence registry. Neither is required to use the verified capture/report workflow today. Linked-worktree metadata support would require deliberate bounded-target validation, not silently following Gitfile paths.
4. Keep all cloud/CI work as development scaffolding. All capture, comparison, verification, reporting and inventory functions must remain usable locally without cloud accounts or services.
