# Interactive workbench frontend QA

## Implementation

Vanilla semantic HTML, external local CSS/JS only. No package install, web fonts, analytics, external network, or generated raster assets in the shipped application. The server supplies all policy text, counts, verdicts, case details and limitations. Configuration edits invalidate previous results. Errors preserve the previous result with an explicit warning and disable export. Execution disables configuration and duplicate submission. Request/revision guards reject stale responses; fetch has a 30-second timeout. `policy_review_valid: false` blocks execution.

## Design system

Private image-generated concept reviewed before implementation: navy fixed left navigation, cool light-gray canvas, white document surfaces, restrained teal action, side-by-side line-numbered policy comparison, independent FAQ/API radio controls, results as a true table with an inline evidence inspector. Tokens: navy #111e38, teal #00877d, canvas #f2f5f9, text #15233b, border #dce3ec, 8px section radius. System sans fonts, 32px title, 20px section titles, 12–14px body and control text. No product imagery required.

The concept's invented privacy-retention paragraph is intentionally replaced by actual registered returns-policy text. The concept's initially selected corrected settings are intentionally replaced by backend defaults (stale/stale). Icons in the concept's navigation are replaced by useful step numbers instead of importing an icon library. Additional required workflow controls are JSON download, verdict filtering, sources/hash disclosure, limitations and actual-state evidence details. These are functional additions, not marketing content.

## Executed checks

- `node --check web/app.js`: passed.
- `node --test tests/frontend/state.test.cjs`: 4 passed. Dependency-free VM/DOM contract checks cover CSRF and exact request body, duplicate request prevention, busy controls, setting invalidation, failure and retry, stale response rejection, policy-review blocking, and no dynamic HTML/external asset references.
- These checks do not verify browser rendering, computed CSS, downloads, keyboard behavior, or actual HTTP integration.

## Browser QA pending

Browser/IAB was attempted first against the local server and returned `net::ERR_CONNECTION_REFUSED`. Installed Playwright/Chromium was then attempted as a fallback. Chromium could not start because `socket() failed: Operation not permitted`; an approved escalated attempt had the same runtime failure. Neither attempt produced an application screenshot. The concept was viewed, but concept-to-browser comparison is **not complete** and no 10/10 visual-fidelity claim is made.

`tests/frontend/workbench.cjs` is ready to run in a browser-capable environment with an already installed Playwright and Chromium. Start `python serve_workbench.py --port 8765`; run `node tests/frontend/workbench.cjs`. Override `CHROMIUM_PATH` or `WORKBENCH_URL` if needed. QA screenshots are written to a new system temporary directory (or QA_OUTPUT_DIR), outside the repository and not shipped. Set CHROMIUM_PATH for an installed browser and PLAYWRIGHT_MODULE_PATH if Playwright is installed outside the project.

The script covers initial state, stale/stale, corrected FAQ only, both corrected, keyboard detail opening, filters, configuration invalidation, error then retry, duplicate click, policy-review block, JSON download, 390px overflow check and page errors. Browser assertions remain unexecuted here.

## Visual comparison ledger to finish

1. Layout: left navy rail and document-led section order match the concept in code; actual rendered spacing remains unverified.
2. Palette: same navy/teal/cool-gray token family, no gradients or imagery; rendered color comparison pending.
3. Typography: intentional system Korean fallback with explicit sizes; real Korean font legibility and line breaks pending.
4. Copy: navigation, title, subtitle, three sections and primary CTA preserved; actual policy and backend status replace concept sample content.
5. Container model: two document columns, compact settings and true results table, no marketing card grid; browser comparison pending.
6. Responsive: <=760px stacks rail/content and documents, table has its own scroll container; 390px render and keyboard focus checks pending.

Do not call the UI visually verified until a real desktop and narrow viewport have been inspected alongside the concept. Validate the long raw state blocks remain usable and selected case focus is visible.
