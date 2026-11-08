"""Offline, synthetic policy-change rehearsal. No LLM or network calls.

FAQ answers are generated from explicitly reviewed structured configuration,
not extracted from prose. Fixture expectations are only read by the evaluator.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from .adapters import digest
from .engine import load_packs, run_pack

ROOT = Path(__file__).resolve().parents[1]


def load_faq(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def faq_answer(config: dict, data: dict) -> dict:
    """Deterministic mock FAQ; receives configuration and business input only."""
    fields = {'order_id': str, 'region': str, 'delivered_on': str,
              'elapsed_days': int, 'opened': bool, 'custom_made': bool}
    decision = None
    if any(data.get(k) is None for k in fields):
        decision = 'NEEDS_INPUT'
    elif any(type(data[k]) is not t for k, t in fields.items()):
        decision = 'INVALID_INPUT'
    elif data['elapsed_days'] < 0 or any(not data[k].strip() for k in ('order_id', 'region', 'delivered_on')):
        decision = 'INVALID_INPUT'
    else:
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', data['delivered_on']):
                raise ValueError('ISO date required')
            dt.date.fromisoformat(data['delivered_on'])
        except ValueError:
            decision = 'INVALID_INPUT'
    if decision is None:
        if data['region'] != config['region']:
            decision = 'UNSUPPORTED'
        elif data['opened'] or data['custom_made']:
            decision = 'INELIGIBLE'
        else:
            window = config['new_window_days'] if data['delivered_on'] >= config['effective_date'] else config['old_window_days']
            decision = 'ELIGIBLE' if data['elapsed_days'] <= window else 'INELIGIBLE'
    return {'status': decision if decision in {'NEEDS_INPUT', 'INVALID_INPUT', 'UNSUPPORTED'} else 'DECIDED', 'decision': decision}


def faq_text(content: dict) -> str:
    return (f"{content['region']} 미개봉 일반 상품: {content['effective_date']} 이후 배송은 "
            f"{content['new_window_days']}일 이내(마지막 날 포함), 이전 배송은 "
            f"{content['old_window_days']}일 이내 반품 가능합니다. 개봉·주문제작 상품은 제외합니다.")


def evaluate_faq(faq: dict, pack: dict) -> dict:
    content = copy.deepcopy(faq['content'])
    sha = digest(content)
    review = faq.get('review', {})
    valid = review.get('content_sha256') == sha and review.get('status') == 'REVIEWED_SYNTHETIC'
    # Reject unsupported configuration instead of silently coercing values.
    try:
        valid = valid and all(type(content[k]) is int and content[k] >= 0 for k in ('old_window_days', 'new_window_days'))
        valid = valid and type(content['region']) is str and bool(content['region'].strip())
        valid = valid and bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', content['effective_date']))
        dt.date.fromisoformat(content['effective_date'])
    except (KeyError, ValueError, TypeError):
        valid = False
    rows = []
    for case in pack['cases']:
        expected = {k: case['expected_after'][k] for k in ('status', 'decision')}
        actual = faq_answer(content, case['business_input']) if valid else None
        errors = [f'{k}: expected {v}, observed {actual.get(k)}' for k, v in expected.items() if actual.get(k) != v] if actual else []
        verdict = 'INCONCLUSIVE' if not valid else ('FAIL' if errors else ('INCONCLUSIVE' if case['intended_behavior'] == 'INDETERMINATE' else 'PASS_WITHIN_SCOPE'))
        rows.append({'id': case['id'], 'input': case['business_input'], 'expected': expected,
                     'response': actual, 'assertion_errors': errors,
                     'assertion_status': 'INCOMPLETE' if not valid else ('FAIL' if errors else 'PASS'),
                     'business_verdict': verdict})
    return {'sha256': sha, 'review_valid': bool(valid), 'review': review, 'content': content,
            'text': faq_text(content) if valid else '설정 또는 검토 hash가 유효하지 않아 FAQ 실행을 보류했습니다.',
            'cases': rows, 'counts': dict(Counter(c['business_verdict'] for c in rows))}


def build_workbench(stale_faq: dict | None = None, corrected_faq: dict | None = None) -> dict:
    pack = load_packs(['customer_service'])[0]
    stale_faq = copy.deepcopy(stale_faq if stale_faq is not None else load_faq(ROOT / 'examples/customer_service/faq_stale.json'))
    corrected_faq = copy.deepcopy(corrected_faq if corrected_faq is not None else load_faq(ROOT / 'examples/customer_service/faq_corrected.json'))
    sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
               for name in ('rehearsal/workbench.py', 'rehearsal/report.py', 'run_workbench.py')}
    stages = []
    for title, config, variant in (
        ('1. FAQ와 API 모두 이전 기준', stale_faq, 'stale_candidate'),
        ('2. FAQ 수정 · API는 이전 기준', corrected_faq, 'stale_candidate'),
        ('3. FAQ와 API 수정 후 재실행', corrected_faq, 'normal'),
    ):
        api = run_pack(pack, variant)
        faq = evaluate_faq(config, pack)
        cases = []
        for api_case, faq_case in zip(api['cases'], faq['cases']):
            verdicts = (api_case['business_verdict'], faq_case['business_verdict'])
            verdict = 'FAIL' if 'FAIL' in verdicts else ('INCONCLUSIVE' if 'INCONCLUSIVE' in verdicts else 'PASS_WITHIN_SCOPE')
            cases.append({'id': api_case['id'], 'business_verdict': verdict})
        counts = dict(Counter(c['business_verdict'] for c in cases))
        readiness = 'BLOCKED' if counts.get('FAIL') else ('REVIEW_REQUIRED' if counts.get('INCONCLUSIVE') else 'PASS_WITHIN_REGISTERED_SCOPE')
        stages.append({'title': title, 'api': api, 'faq': faq, 'cases': cases, 'counts': counts,
                       'readiness': readiness, 'manifest_sha256': digest({'api': api['manifest'], 'faq': faq, 'workbench_sources': sources})})
    evidence = {side: {'path': f'fixtures/customer_service/{relative}',
                      'text': (ROOT / 'fixtures/customer_service' / relative).read_text('utf-8'),
                      'sha256': hashlib.sha256((ROOT / 'fixtures/customer_service' / relative).read_bytes()).hexdigest()}
                for side, relative in pack['source_documents'].items()}
    return {'synthetic_only': True, 'llm_executed': False, 'real_system_connected': False,
            'title': '반품 정책 변경 리허설 · 14일 → 30일', 'evidence': evidence,
            'workbench_sources': sources,
            'oracle_provenance': pack['provenance'], 'expert_reviewed': pack['expert_reviewed'],
            'stages': stages, 'unknowns': [
                '실제 기업 시스템·고객 데이터·LLM·문서 의미 추출은 연결하거나 검증하지 않았습니다.',
                'FAQ 문장은 검토 설정에서 생성합니다. 임의 문서의 의미를 자동 검증하는 기능은 없습니다.',
                '결측·오류·지원 범위 밖 사례는 진단 assertion이 통과해도 업무 판정은 미확인입니다.',
                '등록된 합성 사례만 검증하며 실제 배포 승인을 의미하지 않습니다.',
                '비용·지연·현업 효과는 측정하지 않았습니다.']}
