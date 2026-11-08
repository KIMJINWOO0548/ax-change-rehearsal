# Interactive workbench · implementation scope

This iteration turns the existing offline customer-service report into a local, interactive workbench. It preserves Python-standard-library operation and uses the same independently checked fixtures and state observations. It does not turn mock execution into a real external API, extract arbitrary policy meaning, or authenticate human approval.

## Design decisions

Extend the existing navy/teal, light-surface report vocabulary instead of introducing a marketing site. A compact document-led desktop workspace shows policy before/after, two independently editable simulated artifacts (FAQ and API), and the actual suite results. Use vanilla semantic HTML/CSS/JavaScript served by Python, preserving zero package installation. The user can inspect evidence, choose stale or corrected FAQ/API, run the registered 12 scenarios, filter verdicts, inspect exact response/state evidence, and export the run. Changing settings visibly invalidates the previous result until rerun. Both 14-day and 30-day settings are explanatory mock artifact versions, not writes to an external customer system.

## Backend API

All endpoints are local and response-driven. Server binds 127.0.0.1 only.

GET /api/context returns:
- csrf_token (ephemeral per server process, no persistence)
- project {name, synthetic_only, policy_title, effective_date, scenario_count}
- policy {before, after}, each {path, sha256, text, lines:[{number,text}]}
- change {old_window_days:14,new_window_days:30,effective_date:'2026-12-01', preserved:[...]}
- cases [{id,label,intended_behavior,tags}]
- defaults {faq_version:'stale',api_version:'stale'}
- limits [plain-language limitations]

POST /api/run requires application/json and X-CSRF-Token. Body exactly:
{faq_version:'stale'|'corrected',api_version:'stale'|'corrected'}.
Returns {run_id,created_at,configuration,manifest_sha256,readiness,counts,total,policy,cases,api,faq,limits}.
Cases each {id,label,input,intended_behavior,business_verdict,assertion_status,faq:full FAQ result,baseline:full baseline side,candidate:full candidate side,evidence:[{path,line,quote,sha256}],reason}.
All counts/verdicts derive from the actual existing engine and FAQ evaluator, never frontend constants. Full API and FAQ objects preserve raw evidence. Run id/hash records configuration, sources and output. No mutable backend config or filesystem writes, no external connections. Refresh resets selections in the browser; downloaded runs are user's own artifacts.

POST error {error:{code,message}}. Strict max body 2048 bytes, no unknown fields, no duplicate JSON keys or non-finite numbers. Host must match localhost/127.0.0.1 and active port; if Origin is provided it must equal same origin. Reject cross-site Fetch Metadata, foreign hosts/origins and missing/wrong token. Send security headers and a restrictive CSP. Only fixed static assets, no general file server/directory listing.

## Frontend behavior

Use DOM textContent and element construction for untrusted text. No innerHTML from API strings. Disable submit/config during execution, prevent duplicate clicks, discard stale responses, show request failure and retry without claiming a run completed. Version changes mark displayed results stale. Filters and case details must work by keyboard. Selected case evidence shows response and actual state, not just a verdict badge. Download current full JSON only with user action. Responsive narrow view stacks sections without body overflow. Include no external font/CDN/analytics.

## Verification

Preserve all 39 prior tests. Add four FAQ/API combinations, evidence hash/line validity, malformed API requests, CSRF/Host/Origin/body limits/static path traversal and no file writes. Run HTTP integration tests against ephemeral loopback server. Browser QA covers initial state, stale run, FAQ-only correction, complete correction, case details, filters, repeated clicks, error response, stale result warning, narrow layout, and JSON download when tools permit. Clearly distinguish automated checks from visual checks and mock scope from production readiness.
