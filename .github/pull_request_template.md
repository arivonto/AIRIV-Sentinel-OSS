## Summary

Describe the smallest complete change and why it is needed.

## Contract / boundary

- Relevant contract(s):
- Authority or safety boundary affected:
- Does this change expand production capability or privilege? **Yes / No**

## Verification

- [ ] Focused behavioral tests pass
- [ ] Relevant integration/regression tests pass
- [ ] Full regression passes
- [ ] `./scripts/public_release_secret_scan.sh` passes
- [ ] No `.bak*`, `.pre_*`, `*.identity_backup*`, secrets, or host-local runtime state added

## Production effects

- [ ] This PR does not require a live production effect for repository validation
- [ ] If live validation is separately required, it is governed outside ordinary CI and not implied by merging this PR

## Notes

Include sanitized evidence, migration notes, or compatibility implications. Never include credentials or confidential host data.
