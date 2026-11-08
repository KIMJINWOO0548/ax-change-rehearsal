# 데이터·실행·판정 계약 v1

이 문서와 동봉 JSON 스키마는 초기 구현의 계약이다. 업종 팩의 업무 판정은 패키지에 들어 있는 규정과 독립 작성한 시나리오 정답을 사용한다. 초기 메모리 기반 모의 어댑터는 구현했다. 이 문서의 영속 데이터·권한·승인·API 전체가 구현된 것은 아니며 HANDOFF.md로 범위를 확인한다.

## 1. 객체와 불변 조건

| 객체 | 최소 필드 | 불변 조건 |
|---|---|---|
| ChangeRequest | id, tenant_id, title, owner_id, effective_date, status | 한 작업의 범위를 명시 |
| AssetVersion | id, asset_id, kind, sha256, source_uri, acl_version | 원문·설정 변화는 새 버전 |
| EvidenceSpan | id, asset_version_id, location, extracted_text | 페이지·문단·셀과 버전 연결 |
| RuleCandidate | id, evidence_ids, subject, conditions, value, unit, exceptions, effective_scope, review_status | 모르는 조건은 unresolved로 보존 |
| Dependency | from_id, to_id, type, evidence_ids, method, review_status | 추론 관계를 확인된 의존성으로 표시 금지 |
| TestCase | id, change_id, input, expected_before, expected_after, intended_behavior, oracle_provenance | 기대값은 어댑터 입력에서 제외 |
| RunManifest | id, sha256, asset_versions, adapter_version, model_config, parser_version, index_version, suite_version, seed | 실행 중 버전 교체 금지 |
| Run | id, manifest_hash, environment_id, status, counters | 상태·결과의 단조 전이 |
| Invocation | id, run_id, case_id, side, operation_key, request_digest, status | 재시도에서 같은 논리 작업 키 유지 |
| Observation | invocation_id, snapshot_before, snapshot_after, read_status, observed_at | 어댑터 응답과 별도 관찰 |
| Finding | id, run_id, case_id, category, expected, observed, evidence_ids | 최소 재현 정보 포함 |
| ReviewDecision | id, reviewer_id, manifest_hash, decision, reason | hash 변경 시 기존 결정 만료 |

`kind` 초기 값은 POLICY, FAQ, CONFIG, PROGRAM, AGENT, TEST다. Dependency의 종류는 explains, implements, uses, verified_by로 제한하고 확장 시 마이그레이션한다. 특정 문서가 ‘기준’인지 여부는 파일 종류가 아니라 검토자가 지정한 범위로 판단한다.

## 2. 시간·숫자·미확인 값

- 시나리오의 날짜는 ISO 달력일이고 시험 기준 시간대는 Asia/Seoul이다. 시간 단위가 필요한 실제 연동은 offset을 가진 시각과 IANA 시간대를 추가한다.
- 금액은 KRW 정수, 누적 운전시간과 경과일도 이 첫 합성 팩에서는 정수다. 실수·화폐 변환을 임의 허용하지 않는다.
- 시행일 당일을 포함한다. 변경 전 기준과 후보 기준의 시행 범위는 각 팩의 규정에 명시한다.
- None/null과 누락 필드는 0·false·현재 날짜로 바꾸지 않는다. 알려지지 않은 조건은 모델이 추정하지 않는다.
- 허용하지 않은 음수·타입은 INVALID_INPUT, 필요한 값 미확인은 NEEDS_INPUT, 지원 범위 밖은 UNSUPPORTED다.
- 비교에 필요한 자료를 확보하지 못하거나 관찰이 실패하면 업무 결과는 INCONCLUSIVE다.

## 3. 업무 어댑터

공통 엔진은 아래의 논리 인터페이스를 호출한다. 로컬 Python 구현을 먼저 사용하고 필요할 때 HTTP로 감싼다.

```text
capabilities() -> AdapterCapabilities
create_environment(artifact_version, seed, case_context) -> EnvironmentRef
invoke(environment, operation_key, business_input) -> AdapterResponse
observe(environment, operation_key) -> StateObservation
destroy_environment(environment) -> CleanupResult
```

- capabilities는 입력 스키마·지원 action·관찰 가능한 테이블·어댑터 버전을 반환한다.
- business_input에는 expected_before/after, 정답 경로, 테스트 합격 여부를 넣지 않는다.
- 기준 버전과 후보 버전은 서로 다른 환경에서 실행한다. 각 사례도 초기 상태를 분리한다.
- `operation_key = run_id + case_id + side + logical_action_id`를 하나의 논리 작업 동안 고정한다. 재시도 횟수는 키에 넣지 않는다.
- 요청 digest가 다른데 operation_key가 같으면 CONFLICT다. 중복 요청의 본문을 바꿔 새 작업으로 몰래 수행하지 않는다.
- 상태 변경이 있을 수 있는 timeout은 먼저 observe로 확인한다. 조회도 실패하면 UNKNOWN_EFFECT로 남기고 자동 중복 실행하지 않는다.
- 첫 모의 환경은 네트워크 쓰기를 하지 않는다. 장비·계좌·고객 메시지와 연결하지 않는다.

AdapterResponse는 `decision`, `status`, `message`, `receipt_id`를 포함할 수 있다. `status`는 DECIDED, NEEDS_INPUT, INVALID_INPUT, UNSUPPORTED, ERROR 중 하나다. 업무상 거절은 `DECIDED + INELIGIBLE`처럼 정상적인 업무 판단일 수 있다.

StateObservation은 실제 저장소에서 읽은 스냅샷과 `read_status`를 반환한다. 어댑터의 “한 건 생성했다”는 응답을 그대로 관찰값으로 쓰지 않는다. 관찰자는 최소한 mock DB를 별도 조회한다.

## 4. 시나리오 기대값

동봉 시나리오의 expected_before/after 형식:

```json
{
  "status": "DECIDED",
  "decision": "ELIGIBLE",
  "state_delta": {"table": "return_requests", "count": 1}
}
```

`state_delta.count`는 생성된 행 수의 기대 변화다. 실제 실행에서는 행의 대상·operation_key·payload도 검사한다. 행 개수만 맞고 다른 고객·장비에 기록하면 통과할 수 없다. `fixtures`에는 합성 식별자만 들어 있다.

제조 팩의 모의 작업 테이블은 `work_orders`, 금융 팩의 쓰기 금지 테이블은 `ledger_entries`, 서비스 팩의 접수 테이블은 `return_requests`다. 금융 팩의 기대 변화는 항상 0이다.

합성 문서와 정답은 외부 기관이 보증한 정책이 아니다. `oracle_provenance=authored_synthetic_example`이며 전문가 검증 완료로 승격하지 않는다. 코드가 정답 파일을 읽어 판정하는 어댑터는 금지한다.

## 5. 전후 검증 알고리즘

```text
validate input and pin manifest
for each case:
  create separate baseline and candidate environments
  invoke baseline with business input only
  observe baseline state through independent read
  invoke candidate with the same business input
  observe candidate state through independent read
  compare baseline with expected_before
  compare candidate with expected_after
  compare preserved fields and prohibited effects
  record traces, observations, exceptions and evidence
```

기준 버전 실행은 해당 버전이 유지됐다고 가정하는 반사실적 비교다. 후보 버전은 새 기준의 적용일·예외를 포함한다. ‘새 결과가 이전과 다르다’ 자체는 오류가 아니다.

동봉 `intended_behavior`는 CHANGE, PRESERVE, INDETERMINATE다. CHANGE 사례는 기대 전후 결과가 달라야 하고, PRESERVE는 같아야 한다. INDETERMINATE는 입력 미확인·오류·지원 범위 밖의 처리 시험이다.

입력 미확인을 올바르게 표시했는지 검사하는 **진단 assertion은 PASS**할 수 있다. 그러나 해당 업무 판단의 **business_verdict는 INCONCLUSIVE**다. 보고서에서 둘을 혼동해 업무 성공률을 부풀리지 않는다.

## 6. 판정과 실행 상태를 분리한다

실행 상태: QUEUED → RUNNING → COMPLETED / PARTIAL / FAILED / CANCELLED.

사례의 business_verdict: PASS_WITHIN_SCOPE / FAIL / INCONCLUSIVE.

리포트의 readiness: BLOCKED / REVIEW_REQUIRED / PASS_WITHIN_REGISTERED_SCOPE.

- 어떤 결정적인 assertion이 실패하면 FAIL이다.
- 관찰 불가·파싱 불가·미승인 기준·필수 시험 미실행이면 INCONCLUSIVE다.
- 모든 실행 기록이 있어도 미확인 범위가 남으면 ‘전사 검증 완료’가 아니다.
- 중요한 실패가 있으면 BLOCKED다. 실패 없이 미확인만 있으면 REVIEW_REQUIRED다.
- 등록된 필수 항목과 시험이 모두 검증됐을 때만 해당 등록 범위의 통과를 표시한다.
- 최종 배포 승인과 실행은 이 서비스의 자동 작업으로 연결하지 않는다.

## 7. 실행 도중 변경과 장애

실행은 immutable manifest를 사용한다. 새 문서 업로드나 모델 변경은 새 manifest와 새 run을 만든다. 실행 완료 후 늦게 도착한 이벤트는 원래 run에 기록하되 이미 확정된 판정을 몰래 덮어쓰지 않는다.

작업 상태는 compare-and-swap 또는 트랜잭션 잠금으로 한 worker만 소유한다. 재시작 후 미완료 호출은 먼저 상태를 조회한다. 단순한 retry 숫자로 중복 업무 효과를 해결했다고 주장하지 않는다.

취소는 신규 호출을 중단하고 진행 중 효과는 관찰한다. 이미 실행된 외부 효과를 되돌렸다고 표시하지 않는다. 첫 모의 환경은 결과 보존 후 폐기할 수 있다.

## 8. API 제안

| 동작 | 경로 | 의미 |
|---|---|---|
| 변경 생성 | POST /v1/changes | 범위·소유자·시행일 등록 |
| 자산 버전 등록 | POST /v1/changes/{id}/assets | 파일 hash와 읽기 권한 고정 |
| 조건 후보 추출 | POST /v1/changes/{id}/extractions | 비동기 작업 ID 반환 |
| 기준 검토 | POST /v1/changes/{id}/rule-reviews | 검토자·범위·hash 기록 |
| 영향 후보 조회 | GET /v1/changes/{id}/impact | 관계의 종류와 근거 포함 |
| 시험 계획 생성 | POST /v1/changes/{id}/test-plans | 후보 시험과 누락 영역 |
| 실행 생성 | POST /v1/runs | manifest_hash와 idempotency key 필수 |
| 실행 조회 | GET /v1/runs/{id} | 실행 상태·사례별 판정 |
| 근거 조회 | GET /v1/findings/{id} | 요청자의 자산 권한 재검사 |
| 재검증 | POST /v1/runs/{id}/rechecks | 새 manifest로 새 run 생성 |

동일 idempotency key와 동일 요청은 같은 논리 결과를 돌려준다. 다른 요청이면 409다. 권한 오류는 403 또는 존재 유출 방지 정책에 따른 404다. 비동기 성공 응답은 작업 완료를 의미하지 않는다.

## 9. 보고서 필수 내용

입력 버전, 검토된 기준, 영향 후보/확정 관계, 등록 대상 수, 실제 시험 대상 수, 미확인 대상과 이유, 실패 재현 입력, 기대·관찰 결과, 실제 상태 변화, 비용과 지연, 판정자, 미구현 연동.

핵심 수치는 분자와 분모를 함께 제시한다. 실패가 난 사례를 실행 오류로 바꿔 성공률 분모에서 제외하지 않는다. synthetic/real, observed/inferred를 각 행에 보존한다.


## 10. 현재 구현의 추가 제한과 오류 필드

- 런타임은 빈 시나리오 배열·중복 사례·중복 JSON 키·알 수 없는 계약 필드를 거부한다. 빈 variants/domains 선택도 오류이며 암묵적으로 전체 실행으로 확장하지 않는다.
- 현재 어댑터는 시행일 `2026-12-01`의 동봉 정책만 구현한다. 다른 시행일 메타데이터를 넣으면 실행 전에 거부한다.
- `invocation_error`는 호출 또는 replay 오류, `observation_error`는 초기/호출 후/replay 후 관찰 오류다. 호출 오류만으로 실제 효과가 없다고 판단하지 않는다.
- `first_observed_state`는 최초 호출 직후 상태, `observed_state`는 마지막 관찰 상태다. replay를 하기 전에 최초 결과를 검증하며 replay 이후 상태가 같아야 한다.
- 최초 관찰이 불가능하면 호출하지 않는다. 호출 후 관찰이 불가능하면 불확실한 요청을 replay하지 않는다. `effect_status=UNKNOWN_EFFECT`로 남긴다.
- 현재 timeout 검사는 모의 관찰과 실패 주입이다. 외부 네트워크 호출을 강제 중단하는 시간 제한이나 취소·worker 복구는 구현하지 않았다.
