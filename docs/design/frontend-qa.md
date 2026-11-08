# Review workflow frontend QA

## Implementation and scope
Vanilla semantic HTML and local CSS/JavaScript, with no third-party runtime packages, remote fonts, analytics or assets. Python serves only fixed loopback endpoints. The browser renders actual backend runs. This is a synthetic returns-policy demonstration, not a live enterprise integration or arbitrary policy interpreter.

The workspace follows four steps: policy change, scenario selection, artifact versions, and result/evidence review. The existing navy/teal visual system is preserved. Changed policy text is visible without scrolling through an unchanged paragraph. Desktop uses two-column scenario rows; mobile uses one column, a two-by-two summary, labeled filter rows and an independently scrollable result table.

## Executed checks (2026-11-08)
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
Session history keeps the latest eight runs in memory and resets on reload. Only the registered customer-service scenarios can be selected. Policy-to-case evidence is manually registered; it does not establish comprehensive clause coverage. Partial success never means the omitted scope passed. No real customers, external API, LLM, persistent approval, multi-user authorization or production deployment was tested.
