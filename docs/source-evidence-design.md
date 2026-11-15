# Registered source evidence (T05 first slice)

Build a bounded, dependency-free offline Markdown snapshot and before/after
comparison for the two registered synthetic return policies. The existing runner
uses manually authored policy fixtures; this feature must not derive executable
rules, expected answers, business approval, or external actions from documents.

Approaches considered: a full Markdown/PDF ingestion service would add dependencies,
private-file handling and OCR uncertainty beyond this increment; a plain whole-file
diff would not provide cited block ranges. Selected approach: a conservative block
scanner over registered UTF-8 Markdown, preserving normalized text, line ranges,
content hashes, document hashes and fenced code. Tables and footnotes are labeled
for navigation only, not interpreted as policy semantics. No rendered HTML or UI.

Limits: 256 KiB per file, 4096 lines, 1024 blocks. Decode errors, NUL and limits fail
closed. LF normalization is explicit; raw-byte and normalized-content hashes are
both exposed. Diff aligns exact kind+content hashes with deterministic sequence
matching, not semantic similarity. Moved/reworded content may appear as remove/add.
The complete blocks and equal regions remain available, so the diff cannot hide
unchanged exclusions. Every output states human review required and no approval.

Acceptance: authored paragraphs/table/footnote/code, exact line extraction, duplicate
block anchors, CRLF normalization, insert/delete/replace/equal, repeated alignment,
limits/malformed UTF-8, both registered versions, policy drift, no arbitrary path
selection, unchanged source bytes, CLI error privacy, and full existing regression.
T05 PDF/JSON ingestion, OCR, and T06/T07 semantic review remain unfinished.

## Use and interpretation

```
python inspect_sources.py --policy-version returns-20261201
python inspect_sources.py --policy-version returns-20270115
```

The JSON includes both full source block lists and `changes` with `equal`,
`replace`, `insert` or `delete`. Cite an anchor together with its document hash
and line range. Inspect all changes and unchanged exclusions; a text match is
not a legal/semantic interpretation. Review metadata is not persisted by this
command. It never edits fixtures, calls AI, reads arbitrary files, renders links,
or changes the UI. A schema/parser version is included for snapshots. Labels
are a documented conservative scanner, not full CommonMark compatibility.

Blank/whitespace-only lines are not separate blocks. Block `equal` therefore does
not mean whole-document equality: the result separately reports `raw_bytes_equal`,
`normalized_document_equal`, and `block_sequence_equal`. A blank-line-only change
can preserve every block while changing the normalized document hash. The blocks
are not a lossless serialization of all original whitespace; use the retained
registered source and document hashes when exact complete bytes matter.

The 256 KiB/line/block limits bound the snapshot parser, not every registry I/O:
the existing policy fingerprint verifier reads its fixed registered artifacts in
full before/after inspection. This is not an arbitrary untrusted upload service.
