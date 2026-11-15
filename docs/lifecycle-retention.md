# Durable synthetic execution and segmented retention

## Execution journal
With `--workspace`, `/api/run` commits an `attempt_started` event before invoking the synthetic runner. Existing reports and review events are unchanged. Successful report persistence and `COMPLETED` are committed together. Runner exceptions produce `FAILED`; a completed computation whose report cannot be saved remains `INCOMPLETE`, not a false failure/success. A crash also leaves `INCOMPLETE`. These states do not prove presence/absence of external effects; no real external adapter is implemented.

Pending starts reserve report capacity transactionally. A direct save cannot consume another attempt's reservation. A 4-thread capacity-one test permits exactly one start. There is a separate bounded 1,000-attempt cap and ledger byte/row limits. No event is silently deleted.

Inspect with `python manage_evidence.py --workspace <path> executions` or same-origin `GET /api/executions`. `INCOMPLETE` means not durably completed; a process may still be running. Inspection never retries or rewrites work. Backup and restore preserve the complete journal, including incomplete and failed starts. Old workspaces remain readable; old binaries reject the new event types, so do not downgrade a workspace after recording executions.

## More than 100 reports without eviction
The live-segment cap stays 100; it is not silently increased. Stop the writer, then run:

```
python manage_recovery.py rollover --workspace <old> --archive <new-backup-directory> --destination <new-empty-workspace>
```

The command verifies the old ledger, refuses incomplete attempts, creates and verifies a point-in-time backup, checks that copied journal, then creates a new empty segment. Existing source, backup and report IDs are preserved. All three paths must be separate, and destinations must be new. It does not switch any running server. Restart explicitly with the new workspace; retain the old one and backup. A test saves 100 reports, rolls over, saves report 101 in the new segment and restores all original 100 from the backup.

This is bounded segmented retention, not a unified unlimited-history database. No combined cross-segment UI/search or schema migration is implemented. Stop all writers before rollover: another process can still write to the old source after the snapshot. Failure can leave a verified archive or incomplete new destination for inspection; never delete source data to retry.

## Remaining boundaries
Durable HTTP requests can opt into workspace-scoped idempotency as described below; no-key requests still start separate synthetic runs. The journal records start/end, not individual external call/observe/cancel phases. There is no automatic resumption, real connector cancellation, authenticated multi-user audit or live business accuracy claim. Source edits require server restart under the existing source-drift guard.

## Verification
New lifecycle/retention tests: 14/14, including failure injection, atomic rollback, pending reservation, concurrent capacity, restart/backup/restore and 101-report retention. Full suite and remote CI are reported separately; skipped optional/platform tests are not passes.

Final native checks: full unittest 193 executed, OK with 25 optional/platform skips; frontend 32/32; package structure 3 packs/36 scenarios; CLI help and compileall succeeded. Independent review reproduced and verified fixes for both capacity reservation and unconfirmed-save state. An independent eight-instance/eight-thread capacity-one probe admitted exactly one completed run. No forced process kill/power-loss test was performed. Ledger-row/disk-byte capacity is not fully reserved before computation, so an exhausted write can still remain safely INCOMPLETE rather than finish. CI result is separate from these local checks.


## Durable HTTP request deduplication
`POST /api/run` accepts one `Idempotency-Key` header (1–128 ASCII letters, digits, hyphen or underscore). A workspace is required; ephemeral servers reject keyed requests. The ledger stores its SHA-256 binding with the execution start, not the raw key. Within one workspace, a key and canonical configuration claim exactly one attempt under a SQLite write transaction. Selection order is normalized before binding.

The same key/configuration returns the existing completed report without invoking the runner again, even after reopening the workspace or backup/restore. Its review record reflects the current review revision, not necessarily the original HTTP bytes. A changed configuration or a FAILED/INCOMPLETE attempt returns HTTP 409 EXECUTION_CONFLICT. There is no automatic replay. Inspect `/api/executions` before deciding on a distinct new run. Completed request lookup occurs before capacity checks so a full workspace can still return its saved result.

The UI uses keys only with persistent storage and stores pending keys with synthetic configurations in tab-local `sessionStorage`. A SHA-256 scope derived from the normalized absolute workspace path separates workspaces without exposing the path. Reloading the page and returning to a previous configuration in the same tab reuse its pending key. Only a validated successful response removes that specific entry. A discarded stale response or lost response leaves it recoverable. This is not a cross-tab mutex, authenticated workspace identity, or exactly-once guarantee after closing the tab, changing origin/port, clearing browser storage or replacing/moving the workspace.

The tab store holds at most 64 pending entries across scopes with no silent eviction. Unavailable, malformed, oversized or full storage blocks a new POST rather than issuing an untracked key. A write is read back before sending. If acknowledgement storage fails after the server finished, inspect executions; the pending entry remains available for deduplicated recovery. Do not clear entries to blindly rerun FAILED/INCOMPLETE work. A new browser tab has no shared deduplication intent; copied-tab behavior is browser-dependent.

Rollover uses a new workspace path and therefore a different scope. It neither migrates keys nor deduplicates across old and new segments. Keep the original workspace and inspect its attempts before intentionally running again in the new segment. No-key callers and deliberately new keys remain outside replay protection. Old single-memory-slot page versions must be refreshed to use this behavior.

Compatibility: old ledgers without request bindings remain readable. Old binaries may reject new ledger fields; do not downgrade a workspace. No external adapter, process-kill/power-loss durability or cross-segment/global identity guarantee is claimed.

Validation: dedicated tests cover same-key restart, config conflict, failed/incomplete replay denial, eight concurrent claimers, key validation and canonical selection; real HTTP tests cover replay/conflict and ephemeral rejection. Frontend contract tests cover lost response reuse and intentional/new-configuration keys. Independent reviewer also verified backup/restore replay without a second runner call. Full suite and CI status are reported separately.


### Reload recovery verification
Dependency-free frontend contracts cover reload, changing configuration and returning, workspace isolation, denied/corrupt storage, and success acknowledgement. `tests/browser/session-recovery.cjs` is an optional Playwright-core check against a temporary synthetic workspace and an isolated headless Edge profile, not the user's browser. It forwards requests to the real server then aborts their responses to simulate loss: five HTTP requests produce only two completed executions across reload and configuration changes. A recovered success clears only its entry; corrupt storage sends no POST. Run with an installed `playwright-core` resolved normally or through `PLAYWRIGHT_CORE`; no production data or external adapter is used. Browser crashes, power loss and tab-close restoration remain untested.

## Chronological report binding and interrupted transactions

A completed attempt must reference a report appended after its own start in the
ledger. Configuration equality alone is insufficient: an older unclaimed report
cannot be used as evidence of a later execution. This uses verified sequence order,
not the untrusted wall-clock timestamps. A hash-consistent but chronologically
invalid history is rejected on reopening. Existing valid rows are not migrated.
This is consistency checking, not authentication against a local owner who can
rewrite the entire history.

Controlled subprocess interruption tests now cover two actual process exits:
1. Exit 29 immediately after inserting a report inside its uncommitted SQLite
   transaction. Reopening rolls back the partial report and retains only the
   previously committed INCOMPLETE intent. The original request key cannot rerun,
   and backup/restore preserves that state.
2. Exit 31 after the report and completion transaction commits but before the
   caller receives its response. Reopening and resending the same request key
   returns the one saved report without invoking the runner again.

All reports and inputs are authored synthetic local fixtures. These tests prove
neither power-loss recovery nor exactly-once effects in an external system.
No remote business operation was invoked, and unknown remote effects remain
unknown. This change does not attempt automatic recovery by repeating requests.

Windows verification: lifecycle 15/15; combined lifecycle/idempotency/policy/probe
journal 45/45; full suite 246 tests OK with 25 optional skips; frontend 36/36.
The two chronological-binding tests first failed before the validation guard.
Full suite used normally authorized Windows execution because existing hardlink
fixtures are blocked by the sandbox. Power interruption remains untested.

## Completion-row reservation

Execution starts now reserve ledger rows before invoking a runner: two for a
synthetic report plus its completion, or one for a disposable probe's terminal
record. Reservations are derived from existing INCOMPLETE events under the same
SQLite write transaction, so reopening needs no schema migration or side file.
Direct saves, reviews and other new starts cannot spend those reserved rows.
Successful completion consumes its own reservation; a failed business attempt
uses one terminal row and releases the unused report row. Finished request-key
lookups still return the saved outcome even when no new rows fit.

This supersedes the earlier ledger-row reservation limitation, but not the disk
byte limitation. Filesystem I/O failures, physical disk exhaustion and OS/power
loss can still leave INCOMPLETE evidence. No automatic retry or external-effect
claim has been added. Existing valid history remains readable and unmodified.

Tests first reproduced late invocation without terminal capacity and reservation
loss to a direct save or review. Added cases cover an eight-thread race for the
last three rows, failure release, probe two-row admission and saved replay at the
limit, and mixed business/probe reservations surviving a reopen and completing.

Windows verification: focused lifecycle/idempotency/probe-journal 38/38; full
suite 253 tests OK with 25 optional skips; frontend 36/36. These are local
synthetic checks, not enterprise integration or disk-capacity certification.

Independent review: focused 38/38 and a 99-report plus one pending reservation
boundary passed. The reviewer's full 253-test sandbox run failed only two existing
hardlink fixtures (WinError 5, 25 skips); those two passed separately under normal
Windows permissions. That is not a single independent full-suite pass. The full
253-test successful run above was the implementer's normally authorized run.
Previously over-reserved legacy pending history remains readable but is not
retroactively repaired; new admission protection does not create missing space.

## Replay identity validation

Offline replay validates the required report envelope before starting a new
synthetic run. Original run ID and timezone-aware ISO creation time must remain
valid even though their values are excluded from deterministic comparison. A
missing ID or malformed timestamp is invalid evidence, not MATCH. Attached
`record` review metadata remains outside deterministic evidence and never grants
deployment approval. This adds no remote execution, migration, or rewrite of
existing history; storage integrity must still be checked separately.
