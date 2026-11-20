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

## Policy-registry follow-up

The original fixed customer-service scenario remains the default. Explicit local
configuration can now select `returns-20261201` or `returns-20270115` (see
`contracts/CONTRACTS.md`). The second is an independent authored synthetic
14-to-21-day scenario with a different effective date and eight literal expected
cases; it is not a continuation of a real company policy. Both registered packs,
policy documents and FAQ artifacts are content-pinned. Selected version and
registry source are bound into report manifests. The UI has not been redesigned
or switched to the new scenario automatically.

Completed acceptance scope: immutable registry, explicit selection, date/boundary
and exclusion mutants, old-policy result stability, registered-pack/oracle drift
rejection, same-version replay, old-source INCOMPATIBLE behavior, request-key
version conflict and unfinished-intent reexecution block, plus both-version
backup/restore. General document extraction, an editable policy administration
UI, production business review and multi-user deployment remain unimplemented.

Example local run configuration (through the existing execution API):
```json
{"faq_version":"corrected","api_version":"corrected","policy_version":"returns-20270115"}
```
Use a fresh explicit request key for a new intent; never change keys merely to
bypass an interrupted request. Registered test data contain no real customers.

Verification on Windows: policy-focused 14/14; independently rerun complete suite 242 tests OK with
25 optional skips; frontend 36/36. Package structure validator still checks the
original 3 demo packs/36 cases; the additional registered policy is covered by
the policy tests and is not miscounted as an extra default domain.

The final direct-engine path also deep-copies the selected pack and rechecks
registered artifacts after execution. A newly added drift test failed before
that guard and passed afterwards. Earlier sandbox-only runs hit hardlink
WinError 5 and a transient HTTP socket error; the independent authorized final
Windows run passed all non-skipped tests without loosening assertions.
