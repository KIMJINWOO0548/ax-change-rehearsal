# 데이터·실행·판정 계약 v1

## 2026-11-09 오프라인 통합·재현 무결성 보완

오프라인 작업대도 API·FAQ 실행 결과가 등록된 사례 ID·개수·순서와 정확히
같아야 보고서를 만든다. 빈/누락/중복/잘못된 결과와 알 수 없는 업무 판정은
집계 전에 거부하며 제외된 결과를 통과로 간주하지 않는다.

합성 replay는 canonical JSON의 숫자 표현·불리언과 필드 존재 여부를 구분한다.
키 순서 차이는 허용하지만 타입 또는 증거가 바뀐 결과를 MATCH로 표시하지
않는다. MATCH는 같은 부분 범위·미확인 결과도 재현할 수 있다는 뜻이며
readiness·배포 승인으로 승격하지 않는다. 기존 저장 schema는 변경하지 않는다.
실제 검증과 미검증은 [보완 기록](../docs/COMPLETION_INTEGRITY_2026-11-09.md)에 있다.

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

리포트의 readiness: BLOCKED / REVIEW_REQUIRED / PARTIAL_SCOPE / PASS_WITHIN_REGISTERED_SCOPE.

- 어떤 결정적인 assertion이 실패하면 FAIL이다.
- 관찰 불가·파싱 불가·미승인 기준·필수 시험 미실행이면 INCONCLUSIVE다.
- 모든 실행 기록이 있어도 미확인 범위가 남으면 ‘전사 검증 완료’가 아니다.
- 중요한 실패가 있으면 BLOCKED다. 실패 없이 미확인만 있으면 REVIEW_REQUIRED다.
- 선택한 일부 사례만 통과하고 미확인이 없으면 PARTIAL_SCOPE다. 제외한 사례를 통과로 간주하지 않는다.
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

## 11. 로컬 작업대 HTTP 계약

`serve_workbench.py`는 127.0.0.1에만 바인딩하며 `GET /api/context`와 `POST /api/run`을 제공한다. 이 API는 8절의 영속 제품 API 구현이 아니다. 검증된 합성 정책과 등록된 12개 고객서비스 사례에 한정된다. `faq_version`, `api_version`은 각각 `stale` 또는 `corrected`만 받는다.

정책 before/after는 줄바꿈을 LF로 정규화한 UTF-8 원문 SHA-256과 일치해야 한다. CRLF/CR 변환만 동일하게 취급하며 나머지 내용·공백 변경은 검토를 무효화한다. 응답에 canonicalization=utf8_lf를 기록한다. 새 문서의 의미를 자동 추론하거나 기존 검토를 이어 쓰지 않는다. 근거 줄 번호와 인용은 수동 등록한 정책에 연결된다. 실행 ID는 매번 새로 만들고 구성·규정·평가기 버전 manifest는 재현 가능하게 기록한다.

요청은 정확한 로컬 Host·동일 Origin·세션 내 요청 토큰을 확인한다. 임의 파일 제공, 외부 요청, 디렉터리 목록, 설정 저장은 지원하지 않는다. 이 보호는 로컬 단일 사용자 데모에 한정되며 인증·권한·비밀 보관·운영 서버 방어를 대신하지 않는다.

### 11.1 사례 선택과 실행 범위

기존 요청 `{"faq_version":"corrected","api_version":"corrected"}`은 등록된 12개 사례를 모두 실행한다. 선택 실행은 `case_ids`를 추가한다.

```json
{"faq_version":"corrected","api_version":"corrected","case_ids":["S04","S01"]}
```

- `case_ids`는 1~12개의 문자열로 된 배열이다. 빈 배열, null, 다른 자료형, 중복, 알 수 없는 ID를 실행 전에 거부한다. 대소문자·공백을 자동 보정하지 않는다.
- 실행 순서와 응답 `configuration.case_ids`는 등록 팩 순서로 정규화한다. 위 요청의 실행 순서는 S01, S04다. `case_ids`를 생략한 기존 요청에는 응답 설정에도 해당 필드를 추가하지 않는다.
- 선택한 팩을 API와 FAQ 평가기에 전달한다. 전체 실행 후 결과만 숨기는 방식이 아니다. 두 평가기의 사례 ID와 순서가 선택 범위와 다르면 보고서를 만들지 않는다.
- 응답과 `manifest`, 중첩 `api`에 같은 `scope`를 기록한다. `total`과 `counts`는 선택하여 실행한 사례만 센다.

```json
{
  "registered_total": 12,
  "selected_total": 2,
  "selected_case_ids": ["S01", "S04"],
  "omitted_case_ids": ["S02", "S03", "S05", "S06", "S07", "S08", "S09", "S10", "S11", "S12"],
  "complete": false
}
```

`readiness` 우선순위는 FAIL이 있으면 BLOCKED, 그 외 INCONCLUSIVE가 있으면 REVIEW_REQUIRED, 그 외 일부 범위이면 PARTIAL_SCOPE, 전체 등록 범위이면 PASS_WITHIN_REGISTERED_SCOPE다. API만의 중첩 결과에도 같은 범위 원칙을 적용한다. 따라서 실패·미확인 사례를 선택에서 빼도 전체 준비 완료로 바뀌지 않는다. 전체 등록 범위 통과도 실제 배포 승인을 뜻하지 않는다.

manifest는 정규화한 설정·scope·전체 등록 팩의 `registered_pack_sha256`를 포함한다. `api_manifest.pack_digest`는 실제 실행한 선택 팩의 digest다. 선택 ID의 입력 순서만 바뀌면 같은 manifest를 만들지만, 선택 범위나 제외한 사례 정의가 바뀌면 manifest가 바뀐다. 기존의 정책·FAQ·평가기 소스 hash는 유지한다.

### 11.2 사례 비교 요약

원래의 `faq`, `baseline`, `candidate`, snapshot, error 필드를 유지하고 각 사례에 다음 요약을 추가한다.

```json
{
  "decision_summary": {
    "expected": {"status": "DECIDED", "decision": "ELIGIBLE"},
    "faq": {"status": "DECIDED", "decision": "ELIGIBLE"},
    "baseline_api": {"status": "DECIDED", "decision": "INELIGIBLE"},
    "candidate_api": {"status": "DECIDED", "decision": "ELIGIBLE"}
  },
  "state_summary": {
    "expected_count": 1,
    "observed_count": 1,
    "replay_count": 1,
    "verification": "PASS",
    "checks": {
      "table": true,
      "target": true,
      "operation_key": true,
      "input_digest": true,
      "decision": true,
      "preserved_state": true,
      "replay_unchanged": true
    },
    "errors": []
  }
}
```

`decision_summary.expected`는 후보 정책의 기대 응답이다. 나머지는 실제 각 응답의 status·decision을 그대로 투영한다. 응답이 없으면 해당 객체는 null이고, 응답 객체의 필드가 없으면 그 필드는 null이다. 기대값이나 최종 업무 판정을 실제 응답 대신 채우지 않는다.

`state_summary`는 후보 API에 한정된다. `observed_count`는 초기 snapshot 대비 첫 호출 후 상태 변화량, `replay_count`는 초기 snapshot 대비 재호출 후 상태 변화량이다. 재호출 횟수가 아니며 추가 중복 접수량도 아니다. 해당 snapshot이 없거나 재호출하지 않았으면 null이다. 응답 timeout 뒤 첫 상태만 관찰한 경우 이를 재호출 관찰로 복제하지 않는다.

`verification`은 후보의 응답·상태·재호출 증거를 검증한 assertion 요약이다. 원래 assertion 오류를 보존하고 실제 첫 호출·재호출 snapshot에서 건수, 테이블, 대상, 작업 키, 입력 digest, decision, 기존 상태 보존, 재호출 불변을 확인한다. 건수 일치만으로 PASS가 되지 않는다. 확인된 불일치가 있으면 FAIL, 불일치는 없지만 호출·관찰이 불완전하면 INCOMPLETE다. 필요한 증거가 모두 확인돼야 PASS다. 이는 업무 판정 통과와 다르며 미확인 입력의 진단 검증은 PASS일 수 있다.

`checks`는 true/false/null이다. 실제 관찰이 없거나 비교할 신규 행이 없어 해당 행 검사가 적용되지 않으면 null이다. 쓰기가 없어야 하는 사례의 관찰 건수 0과 재호출 불변이 확인되면 행 관련 check가 null이어도 정상일 수 있다. null을 통과·0·false로 치환하지 않는다. `errors`는 근거에서 확인된 불일치이며, 호출·관찰 실패 세부 정보는 원래 `candidate.invocation_error`, `candidate.observation_error`에 남는다.


## 선택적 로컬 증거 저장 · 0.5.0

`--workspace`를 명시할 때만 저장한다. 서버가 직접 생성한 합성 실행 원본을 저장하며 HTTP로 임의 보고서·정책·파일·URL을 가져오는 API는 없다. 실행 응답에는 저장 성공 뒤에만 `record`가 추가된다. 원본 보고서에는 record를 섞지 않는다.

`record`는 `run_id`, `sha256`, `created_at`, `revision`, `review_status`, `review_is_approval:false`를 가진다. `GET /api/runs`는 요약 목록과 storage 설정을, `GET /api/runs/{run_id}`는 `{report,record,events}`를 반환한다. 기록 식별자는 서버가 만든 UUID다.

`POST /api/runs/{run_id}/review`는 CSRF 검증 후 `{expected_revision,report_sha256,status,note}`만 받는다. `status`는 REVIEWED 또는 CHANGES_REQUESTED, note는 최대 1000문자다. hash/revision 불일치는 409이며 덮어쓰거나 자동 재시도하지 않는다. 초기 상태는 UNREVIEWED다. 메모 변경은 기존 이벤트 수정 대신 새 revision을 남긴다. 리뷰 상태는 업무 판정을 변경하지 않는다.

서버는 모든 저장 작업에서 전체 SQLite ledger와 hash 연결/head를 확인하고 트랜잭션으로 저장한다. 손상은 503, 한도는 409, 없는 실행은 404다. 최대100개 실행, 실행당 최대1000개 검토 이벤트이며 자동 삭제 API는 없다. 저장하지 않은 모드는503 STORAGE_DISABLED다. 상세 위협과 한계는 docs/LOCAL_PILOT.md를 따른다.

기록의 hash 일치·REVIEWED 상태·합성 재현 MATCH는 실제 정책 정확성, 검토자의 신원, 불변 감사, 운영 승인 중 어느 것도 뜻하지 않는다.


## 로컬 복구 bundle · 0.6.0

`manage_recovery.py`는 HTTP가 아닌 로컬 명령이다. `backup --workspace ... --destination ...`, `inspect --source ...`, `restore --source ... --destination ...`를 지원한다. backup/restore destination은 존재하지 않는 별도 경로여야 한다. 대상 경로를 자동 삭제하거나 덮어쓰지 않는다.

Format 1은 정확히 evidence.sqlite3와 manifest.json 두 파일이다. manifest는 format_version, database_sha256, ledger_head, ledger_count, run_count, created_at, encrypted:false, authenticated:false를 포함한다. 알려지지 않은 field/version, 파일 구성, schema, ledger, checksum은 거부한다. 128 MiB DB, 4 KiB manifest, 1 MiB payload, 100개 run 및 run당1000개 review 한도를 적용한다. 정상 저장에서도 logical page size 한도를 commit 전에 확인한다.

inspect는 read-only/immutable 연결로 검증하며 생성자 기반 초기화나 복구를 하지 않는다. restore는 사본 checksum과 원래 검증된 report/review 구조가 모두 일치해야 완료 표식을 제거한다. 실패 폴더는 미완료 상태로 남고, EvidenceStore는 복구 미완료 또는 backup manifest가 있는 경로를 작업 공간으로 열지 않는다.

이 checksum은 snapshot 복사본을 식별하며 실행 중인 원본 파일의 checksum과 동일하다고 주장하지 않는다. 백업은 평문이고 hash는 인증/서명이 아니다. 데이터와 hash 전체를 다시 작성하는 로컬 소유자의 조작, 외부 시스템 상태, 실행 중단 작업이나 저장 전 결과를 복구/증명하지 않는다.


## 선택적 sealed format 1 · 0.7.0

`manage_sealed.py seal/inspect/restore`는 로컬 CLI만 제공한다. password 인수·환경변수·파일·stdin 경로를 제공하지 않고 숨김 TTY에서만 입력받는다. getpass 경고 fallback은 거부하며 argparse 오류도 값/경로를 출력하지 않는다. 최소12 Unicode문자, UTF-8최대1024바이트 검사이며 강도 보장은 아니다.

Header는 big-endian `8s B 16s 12s Q`: magic AXSEALED, version1, salt16, nonce12, ciphertext 길이다. header45바이트 전체가 AAD다. ciphertext는 manifest 길이4바이트, canonical manifest, 원본SQLite bytes를 AES-256-GCM으로 암호화한 내용과16바이트tag다. scrypt profile은 N=131072,r=8,p=1,32bytekey로 고정한다. 입력에서 알고리즘/KDF비용을 받지 않는다.

seal은 source bundle 검증과 실제 read checksum을 확인하고 새 ciphertext 파일만 만든다. inspect는 AEAD와 정확한 형식/manifest/DB checksum만 확인하며 AUTHENTICATED_ENVELOPE 및 database_verified:false다. native in-memory SQLite deserialize는 쓰지 않는다. restore는 인증 후 새 private incomplete 폴더에 원문을 쓰고 기존 파일 기반 schema/ledger 검증을 마친 경우에만 RESTORED_DATABASE_VERIFIED, database_verified:true다. 기존 대상은 덮어쓰지 않는다.

잘못된 비밀번호·태그·checksum은 평문 출력 생성 전에 실패한다. 인증 후 내부DB검사/쓰기 실패는 새 평문 일부와 incomplete 표식이 남을 수 있으며 작업대는 이를 거부한다. 원본·기존평문·복원공간·메모리의 암호화나 안전삭제를 보장하지 않는다. AEAD는 비밀번호 보유자에 대한 byte무결성이지 작성자신원/서명/최신성/조직승인이 아니다.
