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
