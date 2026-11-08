# Interactive workbench frontend QA

## Implementation

Vanilla semantic HTML, external local CSS/JS only. No package install, web fonts, analytics, external network, or generated raster assets in the shipped application. The server supplies all policy text, counts, verdicts, case details and limitations. Configuration edits invalidate previous results. Errors preserve the previous result with an explicit warning and disable export. Execution disables configuration and duplicate submission. Request/revision guards reject stale responses; fetch has a 30-second timeout. `policy_review_valid: false` blocks execution.

## Design system

Private image-generated concept reviewed before implementation: navy fixed left navigation, cool light-gray canvas, white document surfaces, restrained teal action, side-by-side line-numbered policy comparison, independent FAQ/API radio controls, results as a true table with an inline evidence inspector. Tokens: navy #111e38, teal #00877d, canvas #f2f5f9, text #15233b, border #dce3ec, 8px section radius. System sans fonts, 32px title, 20px section titles, 12–14px body and control text. No product imagery required.

The concept's invented privacy-retention paragraph is intentionally replaced by actual registered returns-policy text. The concept's initially selected corrected settings are intentionally replaced by backend defaults (stale/stale). Icons in the concept's navigation are replaced by useful step numbers instead of importing an icon library. Additional required workflow controls are JSON download, verdict filtering, sources/hash disclosure, limitations and actual-state evidence details. These are functional additions, not marketing content.

## Executed checks (2026-11-08)

- Windows, Python 3.12.10: 59 Python tests passed, including actual CRLF policy-file regression coverage; package validator, full demo, static workbench, and compileall passed.
- Node 24.22.1: syntax check and all 4 dependency-free DOM contract tests passed.
- Installed Chrome with an ephemeral Playwright profile and the actual loopback HTTP server: all browser assertions passed. Covered initial state, stale/stale, FAQ-only correction, both corrected, keyboard detail opening, filtering, invalidation, JSON export, server failure and retry, duplicate submission, policy-review blocking, and no page errors.
- Desktop viewport 1488 x 1058 and mobile viewport 390 x 844 screenshots were opened and visually inspected. Korean text, policy comparison, controls, results, evidence and raw-state blocks were readable. Navy navigation, teal action controls, cool-gray canvas and white document surfaces match the documented design system. This is not a pixel-perfect comparison to the private concept or a comprehensive accessibility audit.
- Narrow results tables now retain horizontal scrolling, with a focusable labeled region and visible keyboard/scroll guidance. The detail button stays on one line with an 88px minimum width. A new regression first failed against the old CSS, then passed after the fix: width >=84px, height <=46px, and full button visibility within the scroll container after scrolling. Mobile screenshots were inspected at the detail-column scroll position.

## Issues found and corrected

Windows checkout line endings initially invalidated reviewed policy hashes and blocked normal runs. Policy hashing now declares UTF-8/LF canonicalization, normalizing CRLF and CR only; other text changes still invalidate review. The Windows regression and the existing changed-policy guard both pass.

At 390px, detail buttons initially wrapped Korean text one character per line. Non-wrapping buttons and a 520px table minimum width fix this without creating page-level horizontal overflow. The table remains independently scrollable.

## Reproduction and limits

Start `python serve_workbench.py --port 8765`, then run `node tests/frontend/workbench.cjs` with an already installed Playwright and Chromium. Override CHROMIUM_PATH, PLAYWRIGHT_MODULE_PATH or WORKBENCH_URL when needed. Screenshots go to a new system temporary directory or QA_OUTPUT_DIR, never the public repository.

Cloud browser attempts previously failed because the local browser/server runtime was unavailable; the successful Windows browser run supersedes that pending status. CI covers Ubuntu and Windows with Python 3.10 through 3.13 (eight jobs). Exact CI outcomes are recorded in GitHub Actions for each commit; browser QA remains an explicitly run local check rather than a CI claim. No real enterprise data, external service or LLM performance was tested.
