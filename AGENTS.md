# Repository instructions

- Verify LEGION host before executing; this is an independent recovery workspace, not recovered AMD-DESKTOP Git history.
- Use Python standard library for new helpers; comment rationale and validation assumptions.
- Never modify the game installation, installed addons, or other repositories from this helper. No process interaction. Keep `C:\work\telarafly` read-only.
- Before/after manifests are immutable evidence. Use explicit paths, no implicit newest-baseline selection. Run two post-update captures and compare for consistency.
- Verify tests after edits; refuse incomplete or cross-host comparisons. Document uncertainties rather than guessing.
- Record source roots, time, hashes, coverage, and outcomes. Do not label a patch confirmed until observed.
- Downstream maintainers own remediation and independent validation.
- Preserve original AMD-DESKTOP repository history for eventual explicit reconciliation. No destructive migration or remote publication without authorization.
