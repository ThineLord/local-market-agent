## Change and version

Describe the user-visible problem and resulting behavior. Link the Unreleased changelog entry, or name the release version and bilingual notes for a release PR.

## Validation

- [ ] `ruff check .`
- [ ] `pytest` (network tests remain optional)
- [ ] `python scripts/check_release.py` (add `--tag vX.Y.Z` for a release)
- [ ] `git diff --check`; moved documentation links checked
- [ ] Actual results recorded in `docs/IMPLEMENTATION_LOG.md`
- [ ] No credentials, local databases, or private exports staged; paper-only defaults preserved

## Review and release

- [ ] Final head independently reviewed by a subagent; findings resolved
- [ ] Final-head CI green before subagent merge; expected-head guard used
- [ ] Release PR: package versions, both homepages, changelog, and bilingual release notes agree

List unresolved limitations and deliberately excluded work. Codex coordinates; subagents review and merge; no bot delegation.
