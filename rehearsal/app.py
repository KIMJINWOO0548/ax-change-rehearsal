"""Local workbench service: reviewed synthetic evidence, real mock runs."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import uuid
from collections import Counter

from . import assert_sources_unchanged
from .adapters import ADAPTERS, digest
from .engine import ROOT, check_observation, load_packs, run_pack
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
    '기본은 메모리 실행입니다. --workspace로 켠 로컬 기록만 보존되며, 검토 표식은 인증이나 배포 승인이 아닙니다.',
]


def _policy(pack: dict) -> dict:
    result = {}
    for side, relative in pack['source_documents'].items():
        path = ROOT / 'fixtures' / 'customer_service' / relative
        raw = path.read_bytes()
        # Git and Windows editors may change only line endings. Canonicalize
        # that representation, but preserve all other text for review invalidation.
        text = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
        result[side] = {'path': path.relative_to(ROOT).as_posix(),
                        'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                        'canonicalization': 'utf8_lf', 'text': text,
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
    versions = {'faq_version', 'api_version'}
    require(type(configuration) is dict and versions <= set(configuration)
            and set(configuration) <= versions | {'case_ids'},
            'faq_version과 api_version을 지정하고 선택적으로 case_ids만 추가할 수 있습니다.')
    require(all(type(configuration[key]) is str and configuration[key] in {'stale', 'corrected'}
                for key in versions), '버전은 stale 또는 corrected여야 합니다.')
    if 'case_ids' in configuration:
        selected = configuration['case_ids']
        require(type(selected) is list and 1 <= len(selected) <= 12,
                'case_ids는 1개 이상 12개 이하의 사례 ID 배열이어야 합니다.')
        require(all(type(cid) is str for cid in selected), '사례 ID는 문자열이어야 합니다.')
        require(len(selected) == len(set(selected)), '사례 ID는 중복될 수 없습니다.')


def _readiness(counts: dict, complete: bool) -> str:
    if counts.get('FAIL'):
        return 'BLOCKED'
    if counts.get('INCONCLUSIVE'):
        return 'REVIEW_REQUIRED'
    return 'PASS_WITHIN_REGISTERED_SCOPE' if complete else 'PARTIAL_SCOPE'


def _decision_summary(response: dict | None) -> dict | None:
    # A missing response is not a business decision, including when a write was observed.
    return {key: response.get(key) for key in ('status', 'decision')} if response is not None else None


def _state_summary(side: dict, data: dict, adapter) -> dict:
    """Summarize independent snapshots, never infer state from a response or count alone."""
    initial, first, final = (side[key] for key in ('initial_state', 'first_observed_state', 'observed_state'))
    invocation_error, observation_error = side['invocation_error'], side['observation_error']
    # On an invocation timeout, observed_state is the first snapshot, not a replay.
    replay_attempted = (side['response'] is not None and first is not None
                        and (invocation_error or {}).get('stage') != 'invoke'
                        and (observation_error or {}).get('stage') not in {'initial', 'after'})
    replay = final if replay_attempted else None
    expected = side['expected']
    errors = list(side['assertion_errors'])
    snapshots = [snapshot for snapshot in (first, replay) if snapshot is not None]
    if initial is not None:
        for snapshot in snapshots:
            errors.extend(check_observation(adapter, expected, side['response'], initial,
                                            snapshot, side['operation_key'], data))
    rows = [row for snapshot in snapshots for row in snapshot[len(initial):]] if initial is not None else []
    checks = {
        label: all(row.get(field) == wanted for row in rows) if rows else None
        for label, field, wanted in (
            ('table', 'table', expected['state_delta']['table']),
            ('target', 'target_id', data.get(adapter.target_field)),
            ('operation_key', 'operation_key', side['operation_key']),
            ('input_digest', 'input_digest', digest(data)),
            ('decision', 'decision', expected['decision']),
        )
    }
    checks['preserved_state'] = (all(snapshot[:len(initial)] == initial for snapshot in snapshots)
                                 if initial is not None and snapshots else None)
    checks['replay_unchanged'] = (replay == first if replay is not None and first is not None else None)
    if checks['replay_unchanged'] is False:
        errors.append('idempotent_state_changed')
    complete = (initial is not None and first is not None and replay is not None
                and side['response'] is not None and side['replay_response'] is not None
                and invocation_error is None and observation_error is None)
    verification = 'FAIL' if errors else ('PASS' if complete else 'INCOMPLETE')
    return {
        'expected_count': expected['state_delta']['count'],
        'observed_count': len(first) - len(initial) if initial is not None and first is not None else None,
        'replay_count': len(replay) - len(initial) if initial is not None and replay is not None else None,
        'verification': verification, 'checks': checks, 'errors': sorted(set(errors)),
    }


def _input_fingerprint():
    # This workbench supports only these registered local artifacts. Snapshot
    # their bytes before parsing and recheck before returning evidence. No
    # saved path or arbitrary import controls this list.
    names = ('fixtures/customer_service/pack.json',
             'fixtures/customer_service/policy_before.md',
             'fixtures/customer_service/policy_after.md',
             'examples/customer_service/faq_stale.json',
             'examples/customer_service/faq_corrected.json')
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}


def execute_run(configuration: dict) -> dict:
    assert_sources_unchanged()
    _validate_configuration(configuration)
    input_fingerprint = _input_fingerprint()
    configuration = copy.deepcopy(configuration)
    pack = load_packs(['customer_service'])[0]
    registered_pack_sha256 = digest(pack)
    registered_ids = [case['id'] for case in pack['cases']]
    requested_ids = configuration.get('case_ids', registered_ids)
    require(all(cid in registered_ids for cid in requested_ids), '등록되지 않은 사례 ID가 있습니다.')
    selected_ids = [cid for cid in registered_ids if cid in requested_ids]
    omitted_ids = [cid for cid in registered_ids if cid not in requested_ids]
    scope = {'registered_total': len(registered_ids), 'selected_total': len(selected_ids),
             'selected_case_ids': selected_ids, 'omitted_case_ids': omitted_ids,
             'complete': not omitted_ids}
    if 'case_ids' in configuration:
        configuration['case_ids'] = list(selected_ids)
    # Restrict inputs before either engine runs. Omitted cases never invoke an adapter.
    pack = copy.deepcopy(pack)
    pack['cases'] = [case for case in pack['cases'] if case['id'] in selected_ids]
    policy = _policy(pack)
    require(all(policy[side]['sha256'] == sha for side, sha in REVIEWED_POLICY_HASHES.items()),
            '정책 문서가 바뀌었습니다. 근거와 독립 시나리오를 다시 검토해야 합니다.')
    variant = 'normal' if configuration['api_version'] == 'corrected' else 'stale_candidate'
    api = run_pack(pack, variant)
    api['scope'] = copy.deepcopy(scope)
    api['readiness'] = _readiness(api['counts'], scope['complete'])
    faq_path = ROOT / 'examples/customer_service' / ('faq_' + configuration['faq_version'] + '.json')
    faq_config = load_json(faq_path)
    faq = evaluate_faq(faq_config, pack)
    require([case['id'] for case in api['cases']] == selected_ids
            and [case['id'] for case in faq['cases']] == selected_ids,
            '실행 결과의 사례 목록이 선택한 범위와 일치하지 않습니다.')
    adapter = ADAPTERS[pack['pack_id']]()
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
        actual_decision = actual.get('decision', '응답 미확인') if actual else '응답 미확인'
        faq_decision = f['response'].get('decision', '응답 미확인') if f['response'] else '검토 필요'
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
                      'candidate': a['candidate'], 'evidence': copy.deepcopy(evidence), 'reason': reason,
                      'decision_summary': {'expected': _decision_summary(a['candidate']['expected']),
                                           'faq': _decision_summary(f['response']),
                                           'baseline_api': _decision_summary(a['baseline']['response']),
                                           'candidate_api': _decision_summary(a['candidate']['response'])},
                      'state_summary': _state_summary(a['candidate'], a['input'], adapter)})
    counts = dict(Counter(c['business_verdict'] for c in cases))
    readiness = _readiness(counts, scope['complete'])
    sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
               for name in ('rehearsal/app.py', 'rehearsal/workbench.py')}
    manifest = {'configuration': copy.deepcopy(configuration), 'api_manifest': api['manifest'],
                'scope': copy.deepcopy(scope), 'registered_pack_sha256': registered_pack_sha256,
                'faq_sha256': faq['sha256'], 'faq_artifact_sha256': digest(faq_config),
                'faq_review': faq['review'], 'policy_sha256': {s: p['sha256'] for s, p in policy.items()},
                'service_sources': sources}
    assert_sources_unchanged()
    require(input_fingerprint == _input_fingerprint(),
            'Execution inputs changed; restart and review before running.')
    return {'run_id': uuid.uuid4().hex, 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'configuration': configuration, 'manifest_sha256': digest(manifest), 'manifest': manifest,
            'synthetic_only': True, 'readiness': readiness, 'scope': scope,
            'counts': counts, 'total': len(cases),
            'policy': policy, 'cases': cases, 'api': api, 'faq': faq, 'limits': list(LIMITS)}
