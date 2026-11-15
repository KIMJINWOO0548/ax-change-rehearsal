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
HTTP request resubmission has no idempotency key and may start a separate synthetic run. The journal records start/end, not individual external call/observe/cancel phases. There is no automatic resumption, real connector cancellation, authenticated multi-user audit or live business accuracy claim. Source edits require server restart under the existing source-drift guard.

## Verification
New lifecycle/retention tests: 14/14, including failure injection, atomic rollback, pending reservation, concurrent capacity, restart/backup/restore and 101-report retention. Full suite and remote CI are reported separately; skipped optional/platform tests are not passes.

Final native checks: full unittest 193 executed, OK with 25 optional/platform skips; frontend 32/32; package structure 3 packs/36 scenarios; CLI help and compileall succeeded. Independent review reproduced and verified fixes for both capacity reservation and unconfirmed-save state. An independent eight-instance/eight-thread capacity-one probe admitted exactly one completed run. No forced process kill/power-loss test was performed. Ledger-row/disk-byte capacity is not fully reserved before computation, so an exhausted write can still remain safely INCOMPLETE rather than finish. CI result is separate from these local checks.
