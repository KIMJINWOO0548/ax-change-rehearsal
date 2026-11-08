"""Strict validation for the implemented synthetic pack contract (no dependencies).

Not a general JSON Schema implementation. Business inputs deliberately may be
missing or malformed: those are test stimuli, not invalid pack metadata.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .adapters import ADAPTERS, canonical


PACK_KEYS = set('schema_version pack_id title provenance expert_reviewed effective_date timezone baseline_artifact candidate_artifact source_documents input_fields rules_authority cases'.split())
CASE_KEYS = set('id label business_input expected_before expected_after intended_behavior tags'.split())
DECISIONS = {
    'manufacturing': {'DUE', 'NOT_DUE'},
    'finance': {'WAIVED', 'CHARGED'},
    'customer_service': {'ELIGIBLE', 'INELIGIBLE'},
}
DIAGNOSTICS = {'NEEDS_INPUT', 'INVALID_INPUT', 'UNSUPPORTED'}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f'Non-finite JSON number: {value}')


def load_json(path: Path):
    return json.loads(path.read_text('utf-8'), object_pairs_hook=_unique_pairs,
                      parse_constant=_reject_constant)


def validate_selection(values, allowed, label: str) -> None:
    require(type(values) is list and bool(values), f'{label} must be a nonempty list')
    require(all(type(v) is str and v in allowed for v in values), f'Unsupported {label}')
    require(len(values) == len(set(values)), f'Duplicate {label}')


def _nonblank(value) -> bool:
    return type(value) is str and bool(value.strip())


def validate_pack(pack: dict, root: Path) -> None:
    require(type(pack) is dict and set(pack) == PACK_KEYS, 'Invalid pack fields')
    domain = pack['pack_id']
    require(type(domain) is str and domain in ADAPTERS, 'Unsupported domain')
    adapter = ADAPTERS[domain]()
    require(pack['schema_version'] == '1.0', 'Unsupported schema version')
    require(_nonblank(pack['title']), 'Missing pack title')
    require(pack['provenance'] == 'authored_synthetic_example', 'Unsupported provenance')
    require(pack['expert_reviewed'] is False, 'Unsupported expert-review claim')
    require(pack['timezone'] == 'Asia/Seoul', 'Unsupported timezone')
    require(pack['baseline_artifact'] == 'baseline_v1' and pack['candidate_artifact'] == 'candidate_v2', 'Unsupported artifact versions')
    date = pack['effective_date']
    require(type(date) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', date), 'Invalid effective date')
    dt.date.fromisoformat(date)
    # The current independent adapters implement only this policy date. A metadata
    # edit must not falsely imply that their reviewed implementation also changed.
    require(date == '2026-12-01', 'This mock adapter supports effective_date 2026-12-01 only')
    require(pack['input_fields'] == adapter.fields, 'Input contract does not match adapter')
    require(pack['rules_authority'] == 'source_documents_after_manual_review', 'Unsupported rules authority')
    sources = pack['source_documents']
    require(type(sources) is dict and set(sources) == {'before', 'after'}, 'Invalid source documents')
    domain_root = (root / 'fixtures' / domain).resolve()
    require(domain_root.is_relative_to(root.resolve()), 'Domain directory escapes project')
    for relative in sources.values():
        require(_nonblank(relative) and not Path(relative).is_absolute(), 'Invalid source path')
        source = (domain_root / relative).resolve()
        require(source.is_relative_to(domain_root), 'Source path escapes domain directory')
        require(source.is_file() and source.stat().st_size > 0, 'Missing source document')
    cases = pack['cases']
    require(type(cases) is list and bool(cases), 'Pack must contain at least one case')
    ids = set()
    for case in cases:
        require(type(case) is dict and set(case) == CASE_KEYS, 'Invalid case fields')
        cid = case['id']
        require(type(cid) is str and re.fullmatch(r'[MFS][0-9]{2}', cid), 'Invalid case id')
        require(cid not in ids, f'Duplicate case id: {cid}')
        ids.add(cid)
        require(_nonblank(case['label']), f'Missing label: {cid}')
        data = case['business_input']
        require(type(data) is dict and set(data) <= set(adapter.fields), f'Unknown business input fields: {cid}')
        canonical(data)  # Reject NaN/Infinity and non-JSON values in programmatic calls.
        tags = case['tags']
        require(type(tags) is list and all(_nonblank(t) for t in tags), f'Invalid tags: {cid}')
        require(len(tags) == len(set(tags)), f'Duplicate tags: {cid}')
        for side in ('expected_before', 'expected_after'):
            expected = case[side]
            require(type(expected) is dict and set(expected) == {'status', 'decision', 'state_delta'}, f'Invalid expected fields: {cid}')
            status, decision = expected['status'], expected['decision']
            require(type(status) is str and status in DIAGNOSTICS | {'DECIDED'}, f'Invalid expected status: {cid}')
            require(type(decision) is str and decision in DECISIONS[domain] | DIAGNOSTICS, f'Invalid expected decision: {cid}')
            require((status == 'DECIDED' and decision in DECISIONS[domain]) or (status in DIAGNOSTICS and decision == status), f'Inconsistent expected status: {cid}')
            delta = expected['state_delta']
            require(type(delta) is dict and set(delta) == {'table', 'count'}, f'Invalid state delta: {cid}')
            require(delta['table'] == adapter.table, f'Invalid state table: {cid}')
            require(type(delta['count']) is int and delta['count'] >= 0, f'Invalid state count: {cid}')
            require(delta['count'] == int(decision in adapter.effect_decisions), f'Inconsistent expected effect: {cid}')
        before, after, intent = case['expected_before'], case['expected_after'], case['intended_behavior']
        require(type(intent) is str and intent in {'CHANGE', 'PRESERVE', 'INDETERMINATE'}, f'Invalid intent: {cid}')
        if intent == 'CHANGE':
            require(before != after and before['status'] == after['status'] == 'DECIDED', f'Inconsistent change: {cid}')
        elif intent == 'PRESERVE':
            require(before == after and after['status'] == 'DECIDED', f'Inconsistent preservation: {cid}')
        else:
            require(after['status'] != 'DECIDED', f'Inconsistent indeterminate case: {cid}')
