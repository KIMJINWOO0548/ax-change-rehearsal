# Source-bound local review records (T07 first slice)

The source comparison currently requires human review but cannot retain that
review or show that later edits invalidate it. Add an explicit offline CLI to
record an operator's REVIEWED or CHANGES_REQUESTED statement against the exact
comparison, and verify a record against current files. This does not infer rules,
mark deployment approved, authenticate a reviewer, or run the rehearsal engine.

Choose immutable one-record JSON sidecars rather than changing the evidence-store
schema or a new UI. The caller supplies both source paths, reviewer, status and
note and a new destination. Existing records and user documents are never edited.
Records contain hashes and metadata, not source text or absolute paths. Include
format version and an unkeyed record checksum for accidental corruption detection.
A local owner can rewrite both record and checksum; no signature/authentication.

Verification validates the bounded schema/checksum then recomputes source evidence.
CURRENT means exact source/comparison still matches the statement, not acceptance;
return the recorded status separately. Any source bytes or comparison drift yields
STALE. Invalid records fail closed. Source reads inherit local Markdown limits and
Windows path boundaries. JSON is bounded at 32 KiB, new files are exclusive and
fsynced, failed writes are retained; truncated/invalid records are rejected on later inspection.
A complete but unconfirmed fsync failure still returns no save success; later
verification checks present bytes, not historical crash durability. Output
errors do not disclose paths, source text or notes. Review history is a set of
operator-retained immutable records, not a searchable multi-user audit database.

Acceptance: roundtrip, both statuses, source/line-ending changes, tampered checksum,
unknown fields/duplicate keys, size bounds, destination already exists, no source
or record modification, filename/path safety, private output content, and full
existing regression. POSIX network mounts and hostile concurrent filesystem swaps
retain the source reader's documented limitations. No actual user document will
be committed; tests author their own temporary input.

## Explicit use

```
python review_sources.py record --before before.md --after after.md --destination review-001.json --reviewer "Operator" --status REVIEWED --note "Checked exclusions"
python review_sources.py verify --before before.md --after after.md --source review-001.json
```

Use CHANGES_REQUESTED to record unresolved concerns; it can be CURRENT without
being accepted. Verify exits 0 for CURRENT, 2 for STALE and 1 for invalid/unavailable
input. Record creation exits 0 only after file flush/fsync succeeds. Files use
mode 0600 on POSIX and inherited directory permissions on Windows. Summary output
omits reviewer/note, while the local JSON intentionally retains that entered
metadata. Do not put secrets into a note or publish private review records. A
new review needs a new destination; never replace old review evidence.
