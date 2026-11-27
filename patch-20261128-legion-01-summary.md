# Update Helper verified file-change report

**Stored evidence verified:** both complete post-capture manifests agree.

| Added | Removed | Modified | Unchanged |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 0 | 266 |

## Capture scope

| Field | Value |
| --- | --- |
| Evidence host | LEGION |
| Game installation root | C:\\Program Files \(x86\)\\Glyph\\Games\\RIFT\\Live |
| Stored-evidence verifier host | LEGION |

All regular files in the recorded installation root were hashed. Capture is not an atomic filesystem snapshot. This report verifies stored evidence consistency; it does not establish live game behavior, server availability, addon compatibility or a publisher's patch date.

## Recorded captures

| Capture | Started | Finished | Files | Bytes |
| --- | --- | --- | ---: | ---: |
| before | 2026-11-24T04:46:13.721618+00:00 | 2026-11-24T04:47:24.724674+00:00 | 266 | 26,754,214,661 |
| after-a | 2026-11-27T22:29:09.093262+00:00 | 2026-11-27T22:30:15.479015+00:00 | 266 | 26,754,214,661 |
| after-b | 2026-11-27T22:30:15.487788+00:00 | 2026-11-27T22:31:16.264121+00:00 | 266 | 26,754,214,661 |

## Executable identity

**rift_x64.exe content SHA-256: unchanged.**

| Capture | SHA-256 |
| --- | --- |
| Before | df954b798331e18359be62a31cc74b49fc3f50b87385ebb080a5448256322c01 |
| After | df954b798331e18359be62a31cc74b49fc3f50b87385ebb080a5448256322c01 |

## Downstream review

No installation-file differences were observed between the recorded endpoints. This does not establish that servers did not update or that downstream runtime behavior is unchanged.

## Changed files

None.

## Evidence pins

The supplied baseline pin was checked before reporting. The verifier recomputed both comparisons and checked their exact input-file hashes.

| Evidence | File | SHA-256 |
| --- | --- | --- |
| before | before-20261124-legion.json | 6612cab5ad31162cc0eab21266ed3839c4a2ef1e12e3a2aa82536d5b195c983e |
| after-a | patch-20261128-legion-01-after-a.json | 82e6742c1080df5513f3e55644a55ad488617e8421c29d8806c8ce12cab7effe |
| after-b | patch-20261128-legion-01-after-b.json | 441c78ef438103a4dec72ab9c5df00cc266153331cc16d7c3a726c195db5398b |
| consistency | patch-20261128-legion-01-consistency.json | 0bacebdf637869e772b1afe6eee22d80a7431b04ee8849225d808614260c8a87 |
| changes | patch-20261128-legion-01-changes.json | 6605cec6311d987151b425313fc8d91fe63c7658c936104fc175f3bf3a66b433 |
