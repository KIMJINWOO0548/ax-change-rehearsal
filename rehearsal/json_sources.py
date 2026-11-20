"""Typed, cited local JSON evidence; not policy interpretation or code evaluation."""
import hashlib
import json
from .source_evidence import MAX_BYTES, _read_local_markdown, _file_identity, _local_path
from .storage import sha
from .validation import _unique_pairs, _reject_constant

MAX_NODES = 4096
MAX_DEPTH = 64


class _Number(str):
    """Retain JSON numeric lexemes, never coerce through binary floating point."""


def snapshot_json(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError('Invalid JSON source size or type')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant, parse_int=_Number, parse_float=_Number)
    except RecursionError:
        raise ValueError('JSON source nesting exceeded') from None
    nodes = []

    def visit(item, pointer, depth):
        if depth > MAX_DEPTH or len(nodes) >= MAX_NODES:
            raise ValueError('JSON source structure limit exceeded')
        kind = ('number' if isinstance(item, _Number) else 'null' if item is None
                else 'boolean' if type(item) is bool else 'string' if type(item) is str
                else 'object' if type(item) is dict else 'array' if type(item) is list else None)
        if kind is None:
            raise ValueError('Unsupported JSON value')
        data = {'kind': kind, 'value': None if kind in {'object', 'array'} else str(item) if kind == 'number' else item}
        # Strict UTF-8 hashing also rejects escaped lone Unicode surrogates.
        nodes.append({'pointer': pointer, **data, 'sha256': sha(data)})
        if kind == 'object':
            for key in sorted(item):
                key.encode('utf-8')
                escaped = key.replace('~', '~0').replace('/', '~1')
                visit(item[key], pointer + '/' + escaped, depth + 1)
        elif kind == 'array':
            for index, child in enumerate(item):
                visit(child, pointer + '/' + str(index), depth + 1)

    visit(value, '', 0)
    structural = sha(nodes)
    for node in nodes:
        node['anchor'] = sha({'document': structural, 'pointer': node['pointer'], 'node': node['sha256']})
    return {'format_version': 1, 'raw_sha256': hashlib.sha256(raw).hexdigest(),
            'structure_sha256': structural, 'number_comparison': 'exact JSON numeric spelling',
            'nodes': nodes}


def compare_json(before, after):
    left, right = snapshot_json(before), snapshot_json(after)
    a = {n['pointer']: n for n in left['nodes']}
    b = {n['pointer']: n for n in right['nodes']}
    changes = []
    for pointer in sorted(set(a) | set(b)):
        old, new = a.get(pointer), b.get(pointer)
        state = ('insert' if old is None else 'delete' if new is None
                 else 'equal' if old['sha256'] == new['sha256'] else 'replace')
        changes.append({'pointer': pointer, 'change': state, 'before': old, 'after': new})
    return {'before': left, 'after': right, 'changes': changes,
            'structure_equal': left['structure_sha256'] == right['structure_sha256'],
            'raw_bytes_equal': left['raw_sha256'] == right['raw_sha256'],
            'requires_human_review': True, 'business_validated': False, 'deployment_approval': False,
            'comparison': 'typed JSON pointers; positional arrays; no semantic rule inference'}


def inspect_json_sources(before, after, *, candidates=False):
    left = _read_local_markdown(before, allowed_suffixes=('.json',))
    right = _read_local_markdown(after, allowed_suffixes=('.json',))
    result = compare_json(left[1], right[1])
    try:
        for path, raw, identity in (left, right):
            _local_path(path, allowed_suffixes=('.json',))
            if _file_identity(path.lstat()) != identity:
                raise ValueError('JSON source changed during comparison')
    except OSError:
        raise ValueError('JSON source unavailable') from None
    if candidates:
        result['change_candidates'] = _json_candidates(result)
    return {'provenance': 'unverified_local_files', **result}


MAX_CANDIDATES = 4096


def _json_candidates(evidence):
    """Only called with this module's generated comparison, never imported JSON."""
    from copy import deepcopy
    rows = []
    for change in evidence['changes']:
        if change['change'] == 'equal':
            continue
        if len(rows) >= MAX_CANDIDATES:
            raise ValueError('JSON candidate count limit exceeded')
        binding = {'format_version': 1, 'method': 'typed_json_pointer_candidates',
                   'before_structure': evidence['before']['structure_sha256'],
                   'after_structure': evidence['after']['structure_sha256'],
                   'pointer': change['pointer'], 'change': change['change']}
        rows.append({'candidate_id': sha(binding), **deepcopy(change),
                     'review_status': 'UNREVIEWED', 'executable_rule': None,
                     'ambiguities': ['field_meaning_units_scope_and_exceptions_not_inferred',
                                     'array_indices_are_positions_not_business_identities',
                                     'numeric_spelling_is_not_numeric_equivalence']})
    return {'format_version': 1, 'method': 'typed_json_pointer_candidates',
            'before_structure_sha256': evidence['before']['structure_sha256'],
            'after_structure_sha256': evidence['after']['structure_sha256'],
            'candidates': rows, 'semantic_extraction_complete': False,
            'requires_human_interpretation': True, 'deployment_approval': False}


def build_json_candidates(before, after):
    """Create a separate review queue from strict JSON bytes, never executable rules."""
    return _json_candidates(compare_json(before, after))
