# Disposable HTTP deadline/cancel boundary

`python -m rehearsal.network_probe --port <disposable-service-port> --timeout 5`

This opt-in diagnostic is not registered in the three business fixture packs or
exposed as a workbench API. It contacts only `127.0.0.1` at the explicitly supplied
port, using a fixed GET `/ax-rehearsal/v1/probe` and a random `X-Probe-ID`. Run it
only against a disposable test service you own. It accepts no URL, credentials,
request payload, host name, proxy setting or redirect. A successful response must
be bounded to 8192 bytes and contain exactly `synthetic_only: true`, the matching
`probe_id`, and `value: "ok"`. Strict JSON rejects duplicate keys and non-finite values.
No customer data, vendor API or language model is involved.

A separate spawned worker performs network I/O and parsing. The parent applies a
wall deadline including startup and polls a cancellation event. Ctrl+C in the CLI
requests cancellation. It joins/terminates/kills and checks the local worker exit;
cleanup join budgets add up to 1.7 seconds under normal OS scheduling. Process
startup, terminate/kill calls and OS scheduling cannot themselves be preempted by
this Python deadline. It is not a hard real-time limit; OS process-control failures
may raise rather than return cleanup evidence. If the process
is still alive, the outcome is CLEANUP_FAILED, never success. This is an OS process
boundary, not a sandbox against arbitrary untrusted code.

Before worker startup dispatch is NOT_STARTED. Afterwards it is UNKNOWN until a
REQUEST_SENT event is observed. Partial sends and a response lost after remote
handling remain possible. Every result therefore labels remote_effects UNKNOWN.
Local cancellation does not assert remote cancellation, rollback or absence of
remote work. Tests deliberately show the disposable server continuing after the
local worker has stopped. There is no retry.

Without --workspace, returned PREPARED/start/send/terminal events remain diagnostic
in-memory evidence, not a crash-durable ledger. The optional durable mode below
adds separate diagnostic records to the existing EvidenceStore. Registering production write adapters requires durable
before-effect intent, independent observations, per-operation idempotency and
remote cancellation/cleanup contracts first. None is inferred from these tests.

Verification uses real loopback HTTP with disposable fixtures: valid response,
wall deadline, cancellation before startup and after dispatch, redirect refusal,
oversized response refusal and argument validation. No production provider,
external-host timeout, forced power loss or real business accuracy is verified.

## Native diagnostics and limitations
The local Windows execution host intermittently raises WinError 10014 in raw
socket operations. A fixed 30-case cancellation diagnostic sample recorded 27
passes, two fixture `socket.listen` failures before a probe could run, and one
worker `CONNECT_OR_SEND` failure (errno 14, winerror 10014) before REQUEST_SENT.
That last outcome was correctly FAILED with local cleanup verified and remote
effects UNKNOWN: an already observed connection failure is retained rather than labelled successful
cancellation. The parent now drains at most four already-ready pipe messages before
checking cancellation/deadline. This prioritizes a queued terminal result without
blocking for one. A failure still in flight when cancellation/deadline is observed
can remain unobserved; global event chronology is not guaranteed. No retry/skip was added to mask
these failures. An earlier FAILED sample lacked detailed evidence, so its exact
cause is not retrospectively asserted. The underlying Windows host cause is not
resolved here; CI on a separate host remains important.

Failure evidence preserves stage, exception class and numeric errno/winerror,
but not raw exception text or response content. A controlled peer disconnect and
injected OS error verify this behavior. Initial 6/6 probes and independent 6/6
passed; after diagnostic improvement, 7/7 passed in three recorded runs. These
results do not convert the failed fixed diagnostic sample into a pass.

Final native full regression after diagnostic additions ran 210 tests and failed
with four WinError 10014 errors (25 optional/platform skips): one new probe fixture
listen and three existing HTTP client connect errors. This is not a passing run.
The earlier pre-diagnostic full run was 208 tests OK with 25 skips. The final pure
OS-error evidence test passed independently. Remote CI must be checked separately;
no test skip or retry has been introduced for these host failures.


Independent review identified a queued-terminal/cancel race in the initial
implementation. A bounded nonblocking drain and deterministic queued-OS-failure
regression were added. This does not claim to reconstruct the ordering of an
unobserved remote failure and local cancellation.

The terminal drain does not accept a response as completed after the parent
observes deadline expiry: it records TIMED_OUT with RESPONSE_AFTER_BUDGET and
omits the response. A deterministic late-queued-response regression covers this.
This still does not preempt OS startup/termination calls or establish remote
chronology. Queued failures retain their failure evidence; in-flight outcomes
can remain unknown when cancellation wins.

After the queued-failure and late-response corrections, the final native full run
was 212 tests OK with 25 skips. Independent pure race/error evidence checks were
3/3; the preceding live-plus-pure review was 9/9. These later results do not erase
the earlier Windows-host failures documented above. Remote CI is a separate gate.


## Optional durable diagnostic mode
`python -m rehearsal.network_probe --port <test-port> --timeout 5 --workspace <workspace> --request-key <stable-non-secret-key>`

Both extra options are required together. The existing SQLite hash chain now
accepts separate `probe_started` and `probe_finished` events. Before spawning a
worker, the start is committed with the validated port/deadline and a namespaced
request-key hash. The committed attempt ID also becomes the HTTP probe nonce;
a completed response must match it. No customer input or arbitrary endpoint is
accepted. This does not turn the diagnostic into a business adapter.

`INCOMPLETE` means the final outcome was not durably confirmed. Runner exceptions,
process interruption and storage/validation failure after startup leave it there.
A repeated key cannot execute it again. A finished diagnostic is `RECORDED`, not
business `COMPLETED`: inspect its separate outcome.status and remote_effects.
CANCELLED, TIMED_OUT, FAILED and CLEANUP_FAILED are preserved, with remote effects
UNKNOWN. Repeating a recorded request returns its saved outcome without another
network request, including after reopening or backup/restore. Changing port or
deadline with the same key conflicts. Different keys are new explicit intents;
keys are scoped to the workspace, not globally to a service.

`manage_evidence.py --workspace <workspace> executions` and the existing read-only
`/api/executions` include these typed diagnostics. They never appear as business
reports or pass counts. Backup/restore preserves their ledger; rollover refuses
an incomplete diagnostic. The existing total attempt and ledger bounds still
apply; pending diagnostics conservatively reserve capacity with other attempts.
No existing rows or files are deleted or migrated. Older binaries reject the new
events; do not downgrade a used workspace.

Only the pre-start intent and final outcome are durable, not every intermediate
network event. A crash between send and final commit remains INCOMPLETE, not
assumed cancelled or safe to repeat. Full forced-crash/power-loss recovery and
production HTTP cancellation contracts are not tested. The unkeyed local ledger
is integrity checking, not authentication against its owner rewriting history.

Durable-mode verification: native full regression 223 tests OK with 25 skips;
frontend 36/36; package structure 3 packs/36 scenarios. Independent Windows review
reproduced 11/11 focused tests, including real loopback completion/cancellation
replay, pre-start persistence, injected save failure, concurrent claim, backup/
restore and rollover refusal. Actual forced termination, power failure and real
disk-full conditions have not been verified. No enterprise service was connected.

### Cleanup recovery follow-up

A failed `terminate()` syscall no longer skips the bounded `kill()` fallback.
OS errors from termination/join do not prove cleanup: the worker must actually
be observed dead. A surviving worker yields `CLEANUP_FAILED`, no response, and
remote effects remain `UNKNOWN`. That result is durably replayed without sending
another request. If a response arrived after the deadline and cleanup also fails,
the late-response marker is preserved without reporting success.

Verification: two failure-injection tests first reproduced the uncaught cleanup
error, then passed after the fix. Four cleanup tests cover fallback, surviving
worker, failed kill with durable replay, and late response plus failed cleanup.
A separate child process exited with code 23 after durable intent and before
network dispatch; reopening retained INCOMPLETE and blocked reexecution.
This is controlled process-exit evidence, not a power-loss or post-send crash test.
The network cancellation tests use only a disposable synthetic localhost service.

Final Windows regression: 228 tests OK (25 skipped); frontend 36/36. The sandboxed
run first failed two existing hardlink-fixture creation tests with WinError 5;
a normally authorized Windows rerun passed without code/test relaxation. Optional
skips and the remaining power-loss/real-disk-full/enterprise tests are not passes.


## Deadline evidence and test interpretation

The total timeout includes process startup, connection, response and parsing.
`WORKER_STARTED` alone proves only that the parent started a process; it does not
prove that the child sent HTTP. A timeout with no observed `REQUEST_SENT` keeps
`dispatch=UNKNOWN`, including when startup consumed the budget. A queued
`REQUEST_SENT` is drained before checking the deadline and preserves `SENT`.
Neither outcome proves remote cancellation or absence of a remote effect.

`DeadlineStageTests` deterministically exercises these parent-loop states with
mock process/clock/channel objects. These tests are not real network evidence.
The existing disposable-loopback timeout integration test still requires an
actual observed send and has not been relaxed or given a larger deadline.
On 2026-11-16 it failed with only PREPARED/WORKER_STARTED/TIMED_OUT in two prior
runs, then passed in an unchanged focused run. This establishes intermittent
failure to observe a send before the budget, not the OS/root scheduling cause.
A later passing run must not be reported as proof that this intermittent issue
was fixed. Preserve each run's failure/pass result separately.
