# Review workflow frontend QA

## Implementation and scope
Vanilla semantic HTML and local CSS/JavaScript, with no third-party runtime packages, remote fonts, analytics or assets. Python serves only fixed loopback endpoints. The browser renders actual backend runs. This is a synthetic returns-policy demonstration, not a live enterprise integration or arbitrary policy interpreter.

The workspace follows four steps: policy change, scenario selection, artifact versions, and result/evidence review. The existing navy/teal visual system is preserved. Changed policy text is visible without scrolling through an unchanged paragraph. Desktop uses two-column scenario rows; mobile uses one column, a two-by-two summary, labeled filter rows and an independently scrollable result table.

## 0.4.0 executed checks (2026-11-08)
- Python 3.12 on Windows: 83 tests passed. Package validation, the complete synthetic demo, offline workbench and compileall passed.
- Node 24: 18 dependency-free comparison and DOM/state tests passed. Both JavaScript files passed syntax checks.
- Built-in browser attempt returned “Browser is not available: iab”. The fallback used installed Chrome with an isolated Playwright profile and the actual loopback server.
- Actual browser checks passed: full/empty/partial selection, search without changing selected scope, keyboard Space retaining checkbox focus, detail close returning focus, stale results, FAQ-only correction, API correction, crossed FAQ regression/API improvement, business regression, failure-only selection, unknown cases, compatible history selection, JSON export, mobile overflow/table navigation, error/retry, duplicate click suppression, malformed-result rejection and policy-review blocking. No page errors.
- Final desktop 1488 x 1058 and narrow 390 x 844 screenshots were opened and visually checked. Labels, policy excerpts, selections, comparison controls, evidence and observed-state summaries are readable. This is not a comprehensive accessibility audit, usability study or performance benchmark.

## Issues found and resolved
- A wide-screen fieldset rule placed every checkbox row in the same grid row, creating unreadable implicit columns. Explicit scenario grid placement fixes it. Browser assertions require readable row width/height and failed before the fix.
- Rebuilding scenario inputs on a checkbox change removed keyboard focus. Selection counters now update without replacing inputs. The live Space/focus regression failed before the fix.
- Aggregate failures hid FAQ regressions when the API improved simultaneously. FAQ and API improvements and regressions are now symmetric, and the regression filter includes new component failures.
- Inconsistent readiness, missing omitted cases, absent mandatory provenance and incomplete expectations could be accepted by presentation helpers. Failing-first tests now verify rejection, and independent re-review confirmed the reported cases are closed.

## Reproduction
Start `python serve_workbench.py --port 8765`. With an already installed Playwright and Chromium, run `node tests/frontend/workbench.cjs`. Set PLAYWRIGHT_MODULE_PATH, CHROMIUM_PATH or WORKBENCH_URL when necessary. Screenshots are written outside the repository to a temporary directory or QA_OUTPUT_DIR.

CI runs Python 3.10 through 3.13 on Ubuntu and Windows. Exact outcomes belong to the commit's GitHub Actions run. Browser QA remains a separately executed local check, not a CI claim.

## Remaining limits
Session comparison history keeps the latest eight runs in memory and resets on reload. Opt-in archive storage is separate and persists reports and unauthenticated review notes. Only the registered customer-service scenarios can be selected. Policy-to-case evidence is manually registered; it does not establish comprehensive clause coverage. Partial success never means the omitted scope passed. No real customers, external API, LLM, persistent approval, multi-user authorization or production deployment was tested.

## 0.5.0 executed checks (2026-11-08)

- Windows Python 3.12.10: 111 tests ran, 109 passed and 2 skipped. POSIX ownership/mode checks do not apply on Windows; the symlink check was skipped because this account lacks Windows symlink privilege. Hardlink rejection was tested. These skips are not security passes.
- Node 24.22.1: all 29 dependency-free frontend tests passed. JavaScript syntax, package validator (3 synthetic packs / 36 scenarios), demo, offline workbench, compileall and whitespace checks passed.
- Installed Chrome with an isolated Playwright profile executed the existing workbench regression and all 10 archive check groups against actual loopback servers. Checked default no-storage mode, opt-in save, reload/server restart, historical/current result separation, review history, literal XSS-looking text, two-tab revision conflicts, uncertain committed responses requiring reread, duplicate POST suppression, malformed response rejection/recovery, keyboard focus/input and 390px layout. No page errors.
- Actual 1440px desktop and 390px mobile screenshots were opened and visually inspected. Archive warnings, separate historical results, revision history, wrapped digests, review labels, focus outline and mobile form controls were readable without body overflow. Screenshots and synthetic private workspace data remain outside the repository.
- Windows execution exposed an SQLite handle leak when connection configuration failed on a corrupt database. The connection now closes on configuration failure, with a dedicated mock regression. Test-only SQLite mutation connections now close explicitly. Symlink and hardlink checks are separate, so unavailable symlink privilege cannot hide hardlink coverage. Browser server startup explicitly uses unbuffered UTF-8 output for portability.

Run `node tests/frontend/archive-browser.cjs` with PLAYWRIGHT_MODULE_PATH and CHROMIUM_PATH pointing to an already installed development browser/toolchain. The script owns isolated temporary servers and workspaces. Browser QA is local, not a CI browser claim. CI outcomes must be checked against the exact commit.

The archive is synthetic local pilot infrastructure only. It has no authenticated reviewers, encryption, signed audit authority, enterprise access control or production deployment approval. No real data, external integrations, performance benchmark, penetration test or comprehensive accessibility audit was performed.


## 0.6.0 executed recovery checks (2026-11-08)

- Windows Python 3.12.10: 139 tests ran, 135 passed and 4 skipped. Two POSIX permission tests and two symlink tests requiring unavailable Windows privilege were skipped, not counted as security passes. Recovery and storage hardlink rejection tests passed separately. The first restricted-process run could not create temporary hardlinks; the final suite ran with normal account privileges.
- Node 24.22.1: all 29 dependency-free frontend tests passed. JavaScript syntax checks, package validator (3 synthetic packs / 36 scenarios), demo, offline workbench, compileall and whitespace checks passed.
- Installed Chrome with isolated Playwright profiles passed the complete legacy workbench regression, all 10 archive browser check groups, and all 7 recovery check groups. Recovery exercised a consistent backup while the original loopback server was running, read-only inspection, restore to a new workspace, unchanged original evidence, exact report/review recovery, separation from current results, and 390px layout. No page errors were observed.
- Desktop and 390px mobile recovery and archive screenshots were opened and visually inspected. Historical warnings, preserved review text, wrapped digests, case scope and mobile form controls are readable. Screenshots, databases and backup manifests remain outside the repository.
- Run `node tests/frontend/recovery-browser.cjs` with the same installed development browser environment as the archive suite. `QA_OUTPUT_DIR` can retain screenshots outside the repository. Both scripts close their own temporary servers and browser instances.

Recovery remains local synthetic pilot infrastructure. Backups are plaintext, unauthenticated, bounded bundles, not encrypted archives or signed audit records. Restore requires a new private destination and never overwrites an existing workspace. No HTTP import, shared service, authenticated reviewer, real company data, external integration or production deployment was tested. Windows ACL isolation must be supplied and verified by the operator; POSIX permission coverage does not establish Windows ACL protection. Browser QA is a local check, not CI browser coverage; inspect the exact commit's eight Ubuntu/Windows Python 3.10-3.13 CI jobs separately.


## 0.7.0 executed sealed-backup checks (2026-11-08)

- Windows Python 3.12.10 in a new isolated virtual environment installed the optional official PyPI binary wheels with the committed hash lock; pip check passed. The standard-library core imported successfully with site packages disabled.
- The full Python suite ran 170 tests: 165 passed and 5 skipped. Two POSIX permission checks and three symlink checks requiring unavailable Windows privilege were skipped, not counted as security passes. The sealed path, symlink and hardlink checks were separated so unavailable symlink privilege cannot hide the other coverage. All storage/recovery/sealed hardlink rejection checks passed under normal account privileges.
- Node 24.22.1 passed all 29 dependency-free frontend tests. JavaScript syntax, package validation (3 synthetic packs / 36 scenarios), demo, offline workbench, compileall and whitespace checks passed.
- Installed Chrome with isolated Playwright profiles passed the complete workbench regression, 10 archive check groups, 7 plaintext recovery check groups, and 7 encrypted-copy recovery check groups. The new drill checks live consistent backup, a new encrypted copy, authenticated-envelope-only inspection, database-verified restoration into a new workspace, unchanged source evidence, exact report/review recovery, historical/current result separation, and 390px layout. No page errors occurred. These browser checks call the library with an explicitly public synthetic fixture phrase; they do not establish Windows terminal hidden-input behavior.
- Actual 1440px desktop and 390px mobile encrypted-copy restoration screenshots were opened and visually inspected. Separate historical warnings, preserved review text, scope, wrapped digests and mobile form controls are readable without body overflow. Screenshots, databases, plaintext bundles and encrypted test files remain outside the repository. Test scripts closed their own browsers and servers.
- A single isolated 12-scenario synthetic measurement used a 90,112-byte database and a 90,482-byte encrypted file. Seal took 0.3848 s, inspect 0.3330 s and restore 0.3472 s. GetProcessMemoryInfo reported 161,456,128 bytes peak process working set, including the full process, with fixed scrypt N=131072, r=8, p=1. The restricted-process attempt could not publish a hardlink; the normal-account run succeeded. This is neither a load benchmark nor proof that maximum-size files fit every machine.

Run `node tests/frontend/sealed-browser.cjs` with the installed development browser variables and PYTHON pointing to the isolated encryption environment. Browser QA remains local, not a CI browser claim. Inspect the exact commit's eight Ubuntu/Windows Python 3.10-3.13 jobs separately.

This is a narrow local synthetic pilot. Encryption protects only the explicitly created encrypted copy; original/backup/restored databases remain plaintext, and failed restore folders may retain plaintext. Envelope inspection does not validate SQLite schema or ledger; restoration validates these before reporting success. There is no authenticated signer/reviewer, Windows ACL guarantee, key escrow, real company data, network service, production certification, maximum-size benchmark or comprehensive accessibility audit.


### Reproducible CI runner scope (2026-11-08)

The current CI matrix explicitly uses `ubuntu-24.04` and `windows-latest`, with all four CPython versions 3.10, 3.11, 3.12 and 3.13 on each runner (eight jobs). No test was removed, disabled or newly skipped for this runner selection. During release verification, the moving `ubuntu-latest` label selected Ubuntu 26.04.1; its official Python 3.10.22 download returned HTTP 504 through the setup action retries and one failed-job rerun, before application tests could execute. The official same-release Ubuntu 24.04 x64 asset was confirmed present. Linux CI is pinned to Ubuntu 24.04 for a reproducible test target; this is an infrastructure/environment selection, not an application defect fix or a claim of Ubuntu 26.04 support. Exact-commit CI results remain the release gate.
