# Local JSON source evidence (T05 JSON slice)

The original T05 input plan includes Markdown and JSON; the current source tools
only accept Markdown. Add a separate read-only JSON comparison CLI so structured
policy/configuration evidence is not incorrectly interpreted as Markdown text.

Snapshots preserve RFC6901 JSON Pointer addresses, typed values, node hashes,
whole structural hashes and raw-byte hashes. Object key order and whitespace do
not affect structure equality. Array positions remain significant; no semantic
move inference. Numbers retain their literal spelling instead of float coercion,
so 1, 1.0 and 1e0 deliberately remain distinct. Strings decode JSON escapes without
Unicode normalization. Null is distinct from a missing pointer and boolean from
number. Duplicate keys, nonstandard NaN/Infinity, invalid UTF-8 and lone surrogates
fail closed. All root JSON value types are supported.

Limits: 256KiB per source, 4096 nodes, depth64. Use the existing explicit local
file boundary and metadata drift checks, including Windows network/reparse path
rejection. No writes/uploads/URL fetch/render/evaluation. The result is unverified
local source evidence and requires human review, never business validation or
rule execution. A separate CLI avoids invalidating existing Markdown comparisons
and review hashes. Markdown review/candidate tools do not automatically accept
these JSON snapshots; cross-format review remains future work.

Acceptance: escaped pointers, object-order/whitespace stability, arrays and empty
containers, number spelling/precision, bool/null/missing differences, duplicate
keys and invalid JSON, resource bounds, exact node hashes, unchanged sources,
local drift rejection, error privacy and existing regression. Existing POSIX
network-mount and hostile concurrent filesystem race limitations still apply.

## Use and interpretation

`python inspect_json_sources.py --before before.json --after after.json`

The output includes source values; keep private JSON output local. The empty
pointer denotes the root, ~1 escapes / in keys, and ~0 escapes ~. Array elements
are compared by index, so insertion can yield replacements at later indexes.
Per-pointer equal compares that node's own type/value; container nodes describe
object/array kind, not equality of all descendants. Use structure_equal for the
whole document and inspect all changed child pointers. Number lexical equality
is intentionally stricter than mathematical equality. UTF-8 BOM is not supported.
No source-review/candidate-review record is automatically issued for JSON input.


## T06 opt-in typed JSON review candidates

`python inspect_json_sources.py --before before.json --after after.json --candidates`
adds a separate `change_candidates` object. Without this option, the comparison
output remains unchanged. Each non-equal JSON Pointer becomes one UNREVIEWED
candidate with complete typed before/after node evidence. Missing is represented
by a null node reference, while JSON null is a node with kind `null`. Container
changes and their descendant changes may both appear; this is not a minimal
semantic edit script. Arrays remain positional, not entity-matched.

IDs bind the method/version, both entire structural document hashes, pointer and
change kind. Reordering object keys or changing whitespace preserves IDs;
changing another document value invalidates them conservatively. Numeric spelling
remains strict. The queue contains source values and should not be published if
those values are private. It never evaluates fields as instructions or connects
to any service. At most 4096 candidates are emitted; excess fails, not truncates.

This is a typed structural review queue, not rule extraction. A key named
`effective_date`, `unit`, `limit`, or `approved` is not interpreted as an effective
date, a unit, a boundary, or permission. Every row has `executable_rule=null`;
semantic extraction remains incomplete and deployment approval is false. Existing
Markdown candidate review records are deliberately not reused or migrated for
this separate format. Recording JSON candidate decisions, semantic interpretation
and generation of executable rules/cases remain future tasks. This slice does not
complete T06 or T07.
