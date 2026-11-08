# Review workflow iteration

## Observed gaps
Version 0.3.0 executes every case, but users cannot select a scope or compare earlier runs. FAQ-only correction leaves the same four failures, so the useful improvement is hidden in the aggregate. Evidence requires reading raw JSON. Long policy paragraphs hide the changed effective-date rule below the fold.

## Implementation plan
Preserve the existing local-only standard-library service and navy/teal visual system. Add a visible registered policy-change summary; searchable, keyboard-accessible scenario selection with explicit omitted scope; readable expected/FAQ/API/state evidence; and a bounded in-memory comparison of up to eight runs. Configuration changes continue to invalidate results. Partial execution cannot establish full-suite readiness. Run comparison requires matching policy, scenario inputs/expectations and implementation sources; altered scope or provenance is not silently compared.

Display failures, improvements, regressions and unknowns separately. A FAQ-only correction can improve the FAQ while the API and overall business result still fail. Failure-only rerun is an explicit selection action, never an automatic write or claim that omitted cases passed.

## Guardrails
No copied third-party code, remote assets, LLM, external service, arbitrary document interpretation, persistent approval or production deployment. UI labels distinguish diagnostic checks from business verdicts. Downloads include actual scope and evidence. Empty selection, stale results, network failures and unknown observations remain visible.

## Verification plan
Pure comparison/selection tests, DOM state tests, backend HTTP integration tests, actual Chrome desktop/narrow keyboard and interrupted-flow checks, privacy review and exact-commit Ubuntu/Windows Python 3.10-3.13 CI. Record actual results separately after execution.
