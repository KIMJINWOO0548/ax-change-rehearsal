"""Compare the recorded inputs and decisions of the two synthetic paths."""
from __future__ import annotations

from datetime import date
import re

from .adapters import digest


VERSION = 1
FIELDS = {
    'order_id': str, 'region': str, 'delivered_on': str,
    'elapsed_days': int, 'opened': bool, 'custom_made': bool,
}
DECISIONS = frozenset({'ELIGIBLE', 'INELIGIBLE', 'NEEDS_INPUT', 'INVALID_INPUT', 'UNSUPPORTED'})
SHA256 = re.compile(r'[0-9a-f]{64}')


def project_context(data):
    if not isinstance(data, dict) or any(type(data.get(name)) is not kind for name, kind in FIELDS.items()):
        return None
    if data['elapsed_days'] < 0 or not data['order_id'].strip() or not data['region'].strip():
        return None
    try:
        if date.fromisoformat(data['delivered_on']).isoformat() != data['delivered_on']:
            return None
    except ValueError:
        return None
    return {name: data[name] for name in FIELDS}


def _decision(response):
    value = response.get('decision') if isinstance(response, dict) else None
    return value if isinstance(value, str) and value in DECISIONS else None


def _state(faq, api):
    if any(side['context_sha256'] is None or side['decision'] is None for side in (faq, api)):
        return 'UNOBSERVED'
    if faq['context_sha256'] != api['context_sha256']:
        return 'CONTEXT_MISMATCH'
    return 'ALIGNED' if faq['decision'] == api['decision'] else 'DIVERGENT'


def compare_case_paths(faq_case, api_case):
    faq_context = project_context(faq_case['input'])
    api_context = project_context(api_case['input'])
    faq = {'context_sha256': digest(faq_context) if faq_context is not None else None,
           'decision': _decision(faq_case['response'])}
    api = {'context_sha256': digest(api_context) if api_context is not None else None,
           'decision': _decision(api_case['candidate']['response'])}
    state = _state(faq, api)
    changed_fields = [key for key in FIELDS if faq_context[key] != api_context[key]] if state == 'CONTEXT_MISMATCH' else []
    return {'version': VERSION, 'state': state, 'changed_fields': changed_fields, 'faq': faq, 'api': api}


def validate_crosscheck(check):
    if (type(check) is not dict or set(check) != {'version', 'state', 'changed_fields', 'faq', 'api'}
            or type(check['version']) is not int or check['version'] != VERSION):
        raise ValueError('Invalid crosscheck format')
    for side in (check['faq'], check['api']):
        if type(side) is not dict or set(side) != {'context_sha256', 'decision'}:
            raise ValueError('Invalid crosscheck path')
        context, decision = side['context_sha256'], side['decision']
        if ((context is not None and (not isinstance(context, str) or not SHA256.fullmatch(context)))
                or (decision is not None and (not isinstance(decision, str) or decision not in DECISIONS))):
            raise ValueError('Invalid crosscheck path')
    expected = _state(check['faq'], check['api'])
    fields = check['changed_fields']
    if (type(fields) is not list or any(type(field) is not str or field not in FIELDS for field in fields)
            or len(set(fields)) != len(fields) or bool(fields) != (expected == 'CONTEXT_MISMATCH')
            or check['state'] != expected):
        raise ValueError('Inconsistent crosscheck result')


LABELS = {
    'ALIGNED': '동일 조건에서 판단 일치',
    'DIVERGENT': '동일 조건에서 판단 불일치',
    'CONTEXT_MISMATCH': '입력 조건이 달라 비교할 수 없음',
    'UNOBSERVED': '입력 또는 응답 미확인',
}
