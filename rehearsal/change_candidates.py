"""Cited lexical change candidates, never executable or approved policy rules."""
from collections import Counter
import datetime as dt
import re
from .storage import sha

MAX_MARKERS = 2048
MAX_CANDIDATES = 1024
UNITS = r'(?:(?:days?|months?|years?|hours?|USD|KRW)(?![A-Za-z])|일|개월|년|시간|원|%)'
MARKER = re.compile(
    r'(?P<date>(?<!\d)\d{4}-\d{2}-\d{2}(?!\d))'
    r'|(?P<number>(?<![\d.,])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?!\d|[.,]\d))'
    r'(?P<unit>[ \t]*' + UNITS + r')?'
    r'|(?P<operator><=|>=|!=|==|<|>|≤|≥|이하|미만|이상|초과)')


def _markers(blocks, budget):
    result = []
    for block in blocks:
        if block['kind'] == 'fenced_code':
            continue
        for match in MARKER.finditer(block['text']):
            budget[0] += 1
            if budget[0] > MAX_MARKERS:
                raise ValueError('Candidate marker limit exceeded')
            kind = ('date_literal' if match['date'] else 'comparison_marker' if match['operator']
                    else 'quantity_literal' if match['unit'] else 'number_literal')
            item = {'kind': kind, 'text': match.group(), 'anchor': block['anchor'],
                    'start': match.start(), 'end': match.end(),
                    'line': block['line_start'] + block['text'][:match.start()].count('\n')}
            if kind == 'date_literal':
                try:
                    dt.date.fromisoformat(match.group())
                    item['calendar_valid'] = True
                except ValueError:
                    item['calendar_valid'] = False
            result.append(item)
    return result


def _unmatched(left, right):
    remaining = Counter((item['kind'], item['text']) for item in right)
    result = []
    for item in left:
        key = (item['kind'], item['text'])
        if remaining[key]:
            remaining[key] -= 1
        else:
            result.append(item)
    return result


def build_change_candidates(evidence):
    """Consume an in-process compare_sources result; no imported review controls code."""
    candidates, budget = [], [0]
    for change in evidence['changes']:
        if change['change'] == 'equal':
            continue
        if len(candidates) >= MAX_CANDIDATES:
            raise ValueError('Candidate count limit exceeded')
        before = _markers(change['before'], budget)
        after = _markers(change['after'], budget)
        anchors = {'before_anchors': [b['anchor'] for b in change['before']],
                   'after_anchors': [b['anchor'] for b in change['after']]}
        ambiguities = ['meaning_scope_and_exceptions_not_inferred',
                       'dates_are_not_confirmed_effective_dates',
                       'numbers_units_and_boundaries_require_interpretation']
        if any(b['kind'] == 'fenced_code' for b in change['before'] + change['after']):
            ambiguities.append('non_prose_requires_review')
        candidates.append({'candidate_id': sha({'format_version': 1, 'change': change['change'], **anchors}),
                           'change': change['change'], **anchors,
                           'before_markers': before, 'after_markers': after,
                           'removed_markers': _unmatched(before, after),
                           'added_markers': _unmatched(after, before),
                           'review_status': 'UNREVIEWED', 'executable_rule': None,
                           'ambiguities': ambiguities})
    return {'format_version': 1, 'method': 'limited_lexical_candidates_not_semantic_rules',
            'candidates': candidates, 'requires_human_interpretation': True,
            'semantic_extraction_complete': False, 'deployment_approval': False}
