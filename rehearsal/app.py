"""Local workbench service: reviewed synthetic evidence, real mock runs."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import uuid
from collections import Counter

from .adapters import digest
from .engine import ROOT, load_packs, run_pack
from .validation import load_json, require
from .workbench import evaluate_faq


# Manually registered document versions, separate from editable artifact settings.
# Changing source text invalidates this demo's review; do not silently interpret it.
REVIEWED_POLICY_HASHES = {
    'before': '7046cbf8d42d0ad363b5584f21062a4620aaddd5230141fb6ce91b5693ae57ba',
    'after': '71f79958873021393a7c8ea03c56a3d313aaaa207eb0ac370e8d00405ea846cd',
}


LIMITS = [
    '합성 규정과 시나리오만 사용합니다. 실제 고객·기업 시스템과 연결되지 않습니다.',
    'FAQ와 API는 별도의 결정적 모의 구현입니다. LLM이나 문서 의미 자동 추출을 실행하지 않습니다.',
    '문서 근거 위치는 등록된 합성 정책에 수동 연결했습니다. 임의 규정의 해석을 보장하지 않습니다.',
    '미확인 3개를 통과로 바꾸지 않습니다. 이 결과는 실제 배포 승인이나 현업 정확도가 아닙니다.',
    '실행은 메모리에 한정됩니다. 서버를 종료하면 별도 저장되지 않으며 필요한 기록은 JSON으로 내려받으세요.',
]


def _policy(pack: dict) -> dict:
    result = {}
    for side, relative in pack['source_documents'].items():
        path = ROOT / 'fixtures' / 'customer_service' / relative
        raw = path.read_bytes()
        text = raw.decode('utf-8')
        result[side] = {'path': path.relative_to(ROOT).as_posix(),
                        'sha256': hashlib.sha256(raw).hexdigest(), 'text': text,
                        'lines': [{'number': n, 'text': line}
                                  for n, line in enumerate(text.splitlines(), 1)]}
    return result


def build_context() -> dict:
    pack = load_packs(['customer_service'])[0]
    policy = _policy(pack)
    return {
        'policy_review_valid': all(policy[side]['sha256'] == sha for side, sha in REVIEWED_POLICY_HASHES.items()),
        'project': {'name': 'AX Change Rehearsal', 'synthetic_only': True,
                    'policy_title': pack['title'], 'effective_date': pack['effective_date'],
                    'scenario_count': len(pack['cases'])},
        'policy': policy,
        'change': {'old_window_days': 14, 'new_window_days': 30,
                   'effective_date': pack['effective_date'],
                   'preserved': ['이전 배송 건은 14일 유지', '개봉·주문제작 제외',
                                 '한국 주문만 지원', '미확인 입력은 보류']},
        'cases': [{key: case[key] for key in ('id', 'label', 'intended_behavior', 'tags')}
                  for case in pack['cases']],
        'defaults': {'faq_version': 'stale', 'api_version': 'stale'},
        'limits': list(LIMITS),
    }


def _validate_configuration(configuration):
    require(type(configuration) is dict and set(configuration) == {'faq_version', 'api_version'},
            'faq_version과 api_version만 지정해야 합니다.')
    require(all(type(value) is str and value in {'stale', 'corrected'}
                for value in configuration.values()), '버전은 stale 또는 corrected여야 합니다.')


def execute_run(configuration: dict) -> dict:
    _validate_configuration(configuration)
    configuration = copy.deepcopy(configuration)
    pack = load_packs(['customer_service'])[0]
    policy = _policy(pack)
    require(all(policy[side]['sha256'] == sha for side, sha in REVIEWED_POLICY_HASHES.items()),
            '정책 문서가 바뀌었습니다. 근거와 독립 시나리오를 다시 검토해야 합니다.')
    variant = 'normal' if configuration['api_version'] == 'corrected' else 'stale_candidate'
    api = run_pack(pack, variant)
    faq_path = ROOT / 'examples/customer_service' / ('faq_' + configuration['faq_version'] + '.json')
    faq_config = load_json(faq_path)
    faq = evaluate_faq(faq_config, pack)
    cases = []
    # These source references are manually registered, not semantic extraction.
    evidence = [{'path': policy['after']['path'], 'line': n,
                 'quote': policy['after']['lines'][n - 1]['text'],
                 'sha256': policy['after']['sha256']} for n in (5, 7)]
    for a, f in zip(api['cases'], faq['cases']):
        verdicts = (a['business_verdict'], f['business_verdict'])
        verdict = 'FAIL' if 'FAIL' in verdicts else ('INCONCLUSIVE' if 'INCONCLUSIVE' in verdicts else 'PASS_WITHIN_SCOPE')
        assertions = (a['assertion_status'], f['assertion_status'])
        assertion = 'FAIL' if 'FAIL' in assertions else ('INCOMPLETE' if 'INCOMPLETE' in assertions else 'PASS')
        expected = a['candidate']['expected']['decision']
        actual = a['candidate']['response']
        actual_decision = actual['decision'] if actual else '응답 미확인'
        faq_decision = f['response']['decision'] if f['response'] else '검토 필요'
        if verdict == 'INCONCLUSIVE' and not faq['review_valid']:
            reason = 'FAQ 설정 검토가 유효하지 않아 답변 실행과 업무 판단을 보류했습니다. 설정과 검토 hash를 다시 확인해야 합니다.'
        elif verdict == 'INCONCLUSIVE' and assertion == 'INCOMPLETE':
            reason = '실행 또는 상태 관찰이 완료되지 않아 업무 판단을 보류했습니다.'
        elif verdict == 'INCONCLUSIVE':
            reason = '입력 결측·형식 오류·지원 범위 밖은 진단 검사가 통과해도 업무 판단을 보류합니다.'
        elif verdict == 'FAIL':
            reason = f'후보 정책 기대값은 {expected}입니다. FAQ는 {faq_decision}, API는 {actual_decision}이며 저장 상태도 별도로 비교했습니다.'
        else:
            reason = f'FAQ와 API가 등록된 정책 기대값 {expected}에 일치하며, 접수 대상·건수와 재호출 상태도 확인했습니다.'
        cases.append({'id': a['id'], 'label': a['label'], 'input': a['input'],
                      'intended_behavior': a['intended_behavior'], 'business_verdict': verdict,
                      'assertion_status': assertion, 'faq': f, 'baseline': a['baseline'],
                      'candidate': a['candidate'], 'evidence': copy.deepcopy(evidence), 'reason': reason})
    counts = dict(Counter(c['business_verdict'] for c in cases))
    readiness = 'BLOCKED' if counts.get('FAIL') else ('REVIEW_REQUIRED' if counts.get('INCONCLUSIVE') else 'PASS_WITHIN_REGISTERED_SCOPE')
    sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
               for name in ('rehearsal/app.py', 'rehearsal/workbench.py')}
    manifest = {'configuration': configuration, 'api_manifest': api['manifest'],
                'faq_sha256': faq['sha256'], 'faq_artifact_sha256': digest(faq_config),
                'faq_review': faq['review'], 'policy_sha256': {s: p['sha256'] for s, p in policy.items()},
                'service_sources': sources}
    return {'run_id': uuid.uuid4().hex, 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'configuration': configuration, 'manifest_sha256': digest(manifest), 'manifest': manifest,
            'synthetic_only': True, 'readiness': readiness, 'counts': counts, 'total': len(cases),
            'policy': policy, 'cases': cases, 'api': api, 'faq': faq, 'limits': list(LIMITS)}
