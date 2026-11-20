# Lexical change candidates (T06 first slice)

The source diff has exact citations but does not prioritize policy-like changed
text. Add an optional --candidates view that groups each changed block range into
an UNREVIEWED candidate and extracts literal ISO dates, numbers with optional
units and comparison markers. Every marker retains source anchor, line and exact
text offsets. Unchanged markers are not advertised as additions/removals.

This is a bounded lexical aid, not an LLM, semantic rule extractor or executable
policy generator. A date is not automatically an effective date; a number is not
a threshold; changed text may be a heading, table, example or exclusion. Fenced
code stays visible as changed non-prose but is not scanned for policy markers.
All candidates preserve explicit unknown scope/exceptions/meaning and require
human interpretation. No candidate can approve deployment or alter test oracles.

Prefer optional output over modifying compare_sources: existing comparison hashes
and source-review records remain stable. Candidate IDs bind source anchors and
parser version. Block order and duplicate marker multiplicity are preserved.
Limit total emitted markers to 2048 and candidates to 1024; fail rather than
truncate. ISO date validation only checks calendar syntax. Supported units and
markers are a documented small lexical vocabulary, not multilingual completeness.
T06 full semantic extraction and per-candidate review/history remain unfinished.

Acceptance: date/quantity/operator changes with exact source citations, unchanged
exclusions retained in source diff, duplicates, invalid ISO dates, fenced-code
exclusion, arbitrary text-only changes, resource bounds, CLI opt-in and unchanged
existing review bindings. Use authored synthetic fixtures only in tests.

## Use and limits

```
python inspect_sources.py --policy-version returns-20261201 --candidates
python inspect_sources.py --before before.md --after after.md --candidates
```

Default output and existing source-review fingerprints are unchanged. The optional
change_candidates object has source-bound IDs and exact marker ranges; offsets
refer to normalized block text, not raw file byte offsets. An empty candidate list
is not a semantic unchanged guarantee: whitespace-only changes remain visible in
the parent raw/normalized equality flags, and unsupported syntax is not parsed.

Vocabulary: ISO YYYY-MM-DD dates; signed decimal/comma-grouped numbers; optional
%, days/months/years/hours, USD/KRW and Korean 일/개월/년/시간/원; symbols < <= > >=
!= == ≤ ≥ and Korean 이하/미만/이상/초과. These strings can appear in examples or
unrelated prose and must not be treated as inferred rules. Invalid calendar dates
are retained with calendar_valid=false. All changed blocks remain candidates even
when no supported marker occurs. Unchanged exclusions remain in parent evidence.

Known false positives: addresses such as 123 Main Street, version names such as
v1.2, URL fragments such as /v2/item14 and identifiers/email-like text such as
x14@example can yield number literals. They are not classified as actual policy
thresholds. Review their surrounding source and reject irrelevant candidates.
Malformed numeric chains such as 12,34, 1.2.3 and IPv4-like 192.168.0.1 are not
split into numeric thresholds; ordinary sentence punctuation after 14. or
1,000. is supported. This finite heuristic is not a numeric-language grammar.
