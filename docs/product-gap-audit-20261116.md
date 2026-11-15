# Remaining product requirements: code-backed audit (2026-11-16 KST)

This is ax-change-rehearsal, not Pactra. Baseline is 68718f8. Native synthetic tests passing does not establish enterprise readiness.

| Requirement | Current evidence | Remaining work / acceptance gate |
|---|---|---|
| Versioned policy and adapter packs | engine loads three registered fixture packs; app.build_context selects customer_service; reviewed policy hashes are manually registered; app change summary uses 14/30 days and adapter supports baseline_v1/candidate_v2 | General version registry and independent expected cases, including two different policies/effective dates. Current fixed demonstration is not a general policy engine. |
| External timeout, cancellation, cleanup | adapters explicitly perform no network I/O or language-model calls; observer_timeout is an injected mock variant | Real connector boundary, bounded execution deadline, cancellation and cleanup verification with a disposable service. Do not equate injected observer failure with verified external cancellation. |
| Durable start/call/observe/complete journal | EvidenceStore persists completed reports and review events in SQLite; replay verifies deterministic reports | Persist lifecycle before external effects; interrupted/unknown state recovery tests before introducing real external writes. Current completed-report persistence is not an interrupted-operation journal. |
| Distinguish expected/observed/effects | Completion-integrity branch rejects incomplete evidence, reports INCONCLUSIVE/PARTIAL_SCOPE, inspects mock effects independently | Preserve these contracts when adapters and version packs change; business accuracy remains unvalidated. |
| Retention beyond 100 and migrations | storage.LIMIT=100, excess refuses rather than silently evicting; backup/recovery available; schema user_version=0 enforced | Explicit retention/export policy and forward migration with rollback/backup tests. No arbitrary increase of safety cap. |
| Multi-user permission boundary | Local unauthenticated synthetic workbench | Remains single-owner loopback only. Identity/authentication/access control and concurrent multi-user acceptance required before shared deployment. |
| Windows release and current package | 178 unittest executed (25 skips), Node32, package structure 3 packs/36 scenarios | Actual browser acceptance, optional encryption installed matrix and same-SHA release rebuild/restore test remain separate. Old ZIPs are not current merely because source passed. |

Next safe implementation: version registry plus independent policy fixtures, then durable lifecycle and cancellation before any real connector. This audit deliberately does not claim those tasks implemented.
