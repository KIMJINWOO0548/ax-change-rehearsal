# Per-candidate local review (T07 follow-on)

Whole-document review records do not retain unresolved decisions for individual
lexical change candidates. Add a separate immutable local record for current
candidate IDs. Explicit decisions are CONFIRMED_CHANGE, NOT_A_RULE, or
NEEDS_CLARIFICATION with a nonblank reason; omitted IDs remain PENDING. Unknown
or duplicate IDs fail, preventing stale selections being attached to new sources.

A record binds the full source comparison and candidate generator output. Verify
recomputes both. On drift, report STALE, current review_complete=false, and every
current candidate unreviewed; never carry old decisions forward automatically.
Current completeness only means all nonempty candidates have final dispositions,
not that a rule is executable, correct, authenticated or approved for deployment.
Keep recorded summary separately labeled from the current state.

Implement a CLI record/verify path plus an explicit decisions JSON input. JSON
files remain local, with 512 KiB limits and exact schemas. Records contain IDs,
hashes and supplied reviewer/reasons, not automatically copied source text or
paths. New exclusive destinations only, file flush/fsync, failed files retained.
An unkeyed checksum detects accidental corruption but not owner fabrication.
No UI, database migration, external call or modifications to existing records.
Existing source-review format and hash contract remain unchanged.

Acceptance: partial review/pending preservation, clarification counts, all-final
nonapproval, stale source invalidation, stale/duplicate/unknown selections blocked,
reason bounds/schema/checksum validation, local CLI and no overwrite, and existing
regression. Local filesystem/metadata drift limitations are inherited from source
inspection. This is not signed multi-user review or executable rule extraction.

## Explicit workflow

1. Inspect current files with `inspect_sources.py --before before.md --after after.md --candidates`.
2. Prepare a local decisions JSON array: each row has `candidate_id`, `decision`,
   and a nonblank `reason`. Use only the IDs just inspected. Do not paste source
   secrets into reasons. Omit unresolved candidates to keep them PENDING or use
   NEEDS_CLARIFICATION with the question that remains.
3. Record into a new path:
   `python review_candidates.py record --before before.md --after after.md --decisions decisions.json --reviewer Operator --destination review-001.json`
4. Verify before relying on review state:
   `python review_candidates.py verify --before before.md --after after.md --source review-001.json`.

Verify exit 0 means a CURRENT binding (which may still have pending work), exit 2
means STALE, and exit 1 means invalid/unavailable. Check review_complete separately.
When current candidates are empty, no new per-candidate record is created; use the
whole-source review command for an unchanged-source statement instead. Record
summary omits reviewer/reasons, but the local artifact intentionally retains that
entered metadata. File fsync is not a signed or atomic-publication guarantee;
partial/failed creations remain for inspection. Windows inherits parent ACLs;
POSIX new files use mode0600. No old record is overwritten or auto-migrated.
