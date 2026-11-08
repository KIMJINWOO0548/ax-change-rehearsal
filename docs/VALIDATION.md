# 검증 설계

## 1. 검증 층위

1. 패키지 검사: 파일·참조·스키마·예시 구조. 동봉 검사기의 범위다.
2. 업무 어댑터 검사: 원문 규칙의 구현과 정답 비교. 동봉 36개 합성 사례와 10가지 결함 변형을 실행했으며 results/rehearsal_results.json에 기록했다.
3. 분석 엔진 검사: 조건 추출·영향 후보·시험 계획. 아직 미구현이다.
4. 사용자 가치 검사: 검토시간·놓친 오류·재작업. 아직 미실행이다.

앞 단계의 통과를 뒤 단계의 성능 증명으로 쓰지 않는다.

## 2. 주입할 실패

| 결함 | 주입 위치 | 기대 관찰 |
|---|---|---|
| stale_policy | 후보 프로그램이 기준 버전의 임계값 사용 | 변경 대상의 기대값과 실제값 불일치 |
| stale_faq | 안내 자료만 예전 기준 유지 | 문서 근거와 AI 주장 불일치 |
| stale_index | 후보 AI가 이전 인덱스를 사용 | manifest/근거 버전 불일치 |
| inclusive_boundary | >=를 >로, <=를 <로 변경 | 정확한 경계 사례 실패 |
| wrong_effective_scope | 시행일 이전·기존 배송에도 새 기준 적용 | 유지 사례 실패 |
| exception_removed | VIP·특수 운전·주문제작 조건 삭제 | 예외 사례 실패 |
| false_success | 응답은 성공인데 DB 변경 없음 | 상태 관찰에서 실패 |
| duplicate_effect | timeout 후 재시도로 두 건 생성 | operation_key 기준 중복 발견 |
| wrong_target | 건수는 맞지만 다른 대상에 기록 | 대상 식별자 assertion 실패 |
| unknown_as_zero | null 입력을 0으로 바꿈 | NEEDS_INPUT 기대 사례 실패 |
| observer_timeout | 상태 조회 불가 | 업무 결과 INCONCLUSIVE |
| mixed_revision | 실행 중 문서/모델 버전 바꿈 | manifest 불일치, 재실행 필요 |
| stale_approval | 검토 뒤 규칙을 수정 | 승인 만료, 기존 승인 사용 불가 |
| hidden_dependency | 알려진 관계 하나를 제거 | 정답 관계 누락과 미확인 범위 평가 |
| cross_tenant | 다른 tenant 자산을 검색 후보에 포함 | 근거 노출 전 차단 |
| prompt_instruction | 문서에 검사 무시/외부 실행 지시 삽입 | 문서 텍스트로만 처리, 권한 상승 없음 |

결함을 주입한 harness의 메타데이터는 분석 엔진과 모델에게 보여주지 않는다. 파일명에 `broken`을 넣어 정답을 알려주지 않는다. 같은 정상 원본에서 파생한 자료는 모두 같은 데이터 분할에 둔다.

## 3. 지표 정의

- 영향 정밀도 = 확인된 실제 영향 항목 / 제시한 영향 후보.
- 영향 재현율 = 발견한 실제 영향 항목 / 검토자가 정답으로 확인한 영향 항목.
- 중요한 실패 탐지율 = 발견한 중요한 실패 / 알려진 중요한 실패. 자연 사례와 주입 사례를 분리한다.
- 정상 오탐률 = 오류로 표시한 정상 사례 / 확인된 정상 사례.
- 실행 검증 성공률은 DECIDED 업무 사례를 대상으로 별도 표기하며, 전체 사례의 INCONCLUSIVE 수와 비율도 반드시 같이 표시한다.
- 검토시간은 관계·기대값 수정, 경보 확인·반려, 재시험을 포함한 활성 시간이다. 모델 대기시간도 별도 기록한다.
- 비용은 모델·파서·실행 인프라와 사람의 검토를 포함한다.
- 상태 관찰은 수량·대상·중복·금지된 변경을 검사한다.

표본이 작으면 과도하게 정밀한 소수점과 일반화 주장을 피한다. 원형 변경 묶음 단위로 결과를 묶고, 독립 사례 수를 공개한다.

## 4. 비교와 잠금 평가

B0 사람 검토, B1 일반 LLM, B2 검색+고정 회귀, B3 전체 시스템을 비교한다. B3에서 의미 변경 추출·영향 관계·상태 관찰을 각각 제외한 실험을 수행한다. 모델·입력·실행 예산의 차이를 공개한다.

동봉 36개 시나리오는 공개 개발 예시이므로 잠금 평가에서 제외한다. 새 사례는 모델 프롬프트 튜닝 전에 원형 묶음으로 분할한다. 문장만 바꾼 변형을 독립 현업 사례라고 세지 않는다.

주어진 정책과 관찰만으로 기대 결과를 결정할 수 없으면 보류 정답으로 남긴다. 규정의 법률·안전 적합성 자체를 본 제품의 자동 정답으로 삼지 않는다.

## 5. 모델 결과의 취급

모델·프롬프트·파서·검색·온도·seed와 입력 버전을 기록한다. seed가 같아도 외부 모델 호출이 완전히 결정적이라고 보장하지 않는다. 중요한 AI 사례는 반복 실행해 분산과 최악 사례를 기록한다.

문서 근거가 없는 답변, 조건을 생략한 답변, 다른 버전 인용, API와 다른 결과, 권한 밖 근거를 별도 오류로 분류한다. 문체가 자연스럽다는 이유로 업무 정확도를 통과시키지 않는다.


## 0.2.0 자동 회귀와 확인 범위

```bash
python -m unittest discover -s tests -v
python tools/validate_package.py
python run_demo.py
python run_workbench.py
```

정상 및 10가지 주입 변형의 기대 검출 수를 자동 검사한다. 빈 실행·중복 ID/JSON 키·잘못된 날짜/타입·필수 입력 누락·작업 키 충돌·상태 격리·최초 호출과 재호출 사이의 상태·호출 후 timeout·잘못된 관찰 응답·보고서 escaping을 포함한다.

호출 성공 직후의 상태를 먼저 검증하고, 그 뒤 같은 키로 재호출한다. 재호출이 최초 호출의 누락된 쓰기를 보완하더라도 최초 실패는 지워지지 않는다. 관찰값은 행 객체 배열이어야 하며 null 또는 잘못된 형태는 UNKNOWN_EFFECT다.

FAQ/API 3단계 보고서는 실제 모의 실행 결과에서 만든다. 설정 검토 hash가 달라지면 FAQ 결과는 미확인으로 남는다. 설정 hash는 신원·권한 확인 수단이 아니다.

Windows Python 3.12.10에서 61개 Python 테스트와 4개 DOM 테스트, validator, demo, workbench, compileall을 통과했다. 실제 Chrome에서 1488px/390px 화면과 기능 흐름을 검증하고 스크린샷을 직접 확인했다. Windows 줄바꿈 해시와 모바일 상세 버튼 회귀를 수정했다. 자세한 결과와 한계는 `docs/design/frontend-qa.md`에 있다. GitHub Actions는 Ubuntu/Windows와 Python 3.10~3.13의 8개 조합이며, 정확한 commit별 결과는 실행 기록을 확인한다.

## 0.3.0 로컬 작업대

Python 테스트에는 실제 loopback HTTP 서버를 띄워 실행하는 통합 검사가 포함된다. 네 가지 FAQ/API 설정 조합과 정책 근거·문서 변경 검토 무효화, Host·Origin·Fetch Metadata·CSRF·중복 헤더·본문 크기·잘못된 JSON·임의 파일 경로를 검사한다.

```bash
python -m unittest discover -s tests -v
node --check web/app.js
node --test tests/frontend/state.test.cjs
```

Node는 애플리케이션 실행 의존성이 아니라 프런트엔드 개발 검사용이다. 정식 브라우저 검사는 `tests/frontend/workbench.cjs`로 별도 수행하며, 실제로 실행한 범위는 `docs/design/frontend-qa.md`에 기록한다.

## 0.4.0 선택 범위와 실행 비교

선택한 사례만 실제 FAQ/API 엔진에 전달한다. 전체 등록 팩과 선택된 팩 모두 provenance에 포함하고, 누락 사례를 응답·manifest·중첩 API 결과에 표시한다. 부분 실행의 정상 결과는 PARTIAL_SCOPE이며 전체 검증으로 승격하지 않는다.

상태 요약은 첫 호출과 재호출 뒤의 실제 관찰을 구분한다. 미관찰은 null이며 대상·작업 키·입력 digest·행 내용·기존 상태 보존·재호출 불변성을 함께 검사한다. API/FAQ 사례 ID 누락·불일치도 조용히 자르지 않고 거부한다.

실행 비교는 필수 정책/구현 SHA-256과 전체 등록 팩, 선택 범위, 실제 입력과 기준·후보 기대값이 모두 일치할 때만 제공한다. FAQ 회귀와 API 개선이 동시에 일어나도 개별 검사 회귀를 숨기지 않는다. 잘못된 서버 응답의 준비 상태·집계·미실행 목록은 화면에서 거부한다.

로컬 Windows Python 83개, 프런트엔드 18개 검사가 통과했다. 실제 Chrome에서 선택·비교·교차 회귀·근거·다운로드·키보드·390px 화면·오류 복구를 검사했다. CI 결과는 최종 commit의 실행 기록으로 확인한다.

## 0.5.0 로컬 증거와 검토 메모

클라우드 Python 3.12에서 Python 109개, 의존성 없는 프런트엔드 29개 검사가 통과했다. SQLite 재시작 복원, 전체 ledger/report hash 검증, 보고서·이벤트 변경·삭제·파일 손상, 안전하지 않은 경로/권한, 한도, 동시 revision 충돌, 원본/부분 범위 보존, 저장 비활성 기본값과 HTTP 보안 경계를 포함한다. CLI 검증·목록·재현은 원본 기록이나 검토 상태를 바꾸지 않는다.

코드를 import한 뒤 디스크 소스가 바뀌는 경우와 실행 중 정책 원문·pack·FAQ 입력이 바뀌는 경우를 별도 프로세스에서 재현했다. 수정 전 실패를 확인한 뒤 실행 전후 fingerprint 검사로 반환을 차단했다. 이는 로컬 파일 쓰기 권한자의 악의적 파일 교체·복구 방어가 아니다.

저장 UI는 synthetic 표시, scope/집계/판정, manifest/record binding, 이력 revision/hash, 잘못된 서버 응답을 검증한다. 중복 저장·불확실 저장 응답·지연된 읽기 중 메모 손실도 회귀에 포함한다.

실제 브라우저 재현 스크립트는 `tests/frontend/archive-browser.cjs`다. Playwright와 설치된 Chromium을 개발 환경에서 사용한다. 애플리케이션 실행에는 이 의존성이 필요 없다. 이 파일의 존재나 구문 검사만으로 실제 화면 시험 통과를 주장하지 않는다. 실행 환경별 실측 결과는 `docs/design/frontend-qa.md`에 기록한다.

### 0.5.0 Windows final validation

Windows Python 3.12.10 ran 111 tests: 109 passed and 2 skipped (POSIX permissions and unavailable Windows symlink privilege). Hardlink rejection and corrupt-database connection cleanup were tested. Node 24.22.1 passed all 29 frontend tests. Actual installed Chrome passed the legacy workbench suite and 10 archive browser check groups, including restart persistence, review conflicts and uncertain-response recovery. Desktop/mobile screenshots were opened and inspected. Details and explicit scope limits are recorded in `docs/design/frontend-qa.md`.


## 0.6.0 백업·복원

클라우드 Python 3.12에서 전체138개 테스트, 프런트엔드29개 테스트, 합성팩3개/36사례 검증을 통과했다. 새 복구시험은 동일 report/review 복원, 원본/backup byte 보존, 읽기 전용 검사, 동시쓰기와 WAL snapshot, checksum 재계산 후에도 잘못된 schema/trigger 거부, payload/DB 한도, 미완료 표식, 기존·빈 대상 폴더 보존, 경로/권한, connection closure, Python3.10의 setlimit 부재를 다룬다.

새 실제 UI 복구훈련 스크립트는 tests/frontend/recovery-browser.cjs다. 실제 실행 환경과 결과는 docs/design/frontend-qa.md에 따로 기록하며, 스크립트 구문 검사만으로 화면 검증을 주장하지 않는다. 이 단계는 암호화·서명·SSO/RBAC·실제 기업 데이터나 운영 복구 목표의 검증이 아니다.


### 0.6.0 Windows final validation

Windows Python 3.12.10 ran 139 tests: 135 passed and 4 skipped (two POSIX permission checks and two unavailable Windows symlink-privilege checks). Recovery and storage hardlink tests passed separately. Node 24.22.1 passed all 29 frontend tests. Installed Chrome passed the complete workbench regression, 10 archive check groups and 7 live backup/inspect/new-workspace-restore check groups. Desktop/mobile screenshots were opened and inspected. Validator, demo, offline workbench, syntax, compileall and whitespace checks passed. See `docs/design/frontend-qa.md` for actual coverage and remaining limits. Exact-commit CI remains independently verified across Ubuntu/Windows and Python 3.10-3.13.

## 0.7.0 선택적 암호화 사본

고정 의존성 cryptography50.0.2가 설치된 Linux/Python3.12 격리 환경에서 최신 Python168개(생략없음), 프런트엔드29개,3팩36사례 검증이 통과했다. 기본 코어와 sealed 모듈의 stdlib-only import도 확인했다. CI는8개 네이티브Python/OS조합에서 hash 고정 wheel을 설치하고 encrypted capability를 명시적으로 검사한다.

생산 profile의 full-cost scrypt로 roundtrip, 무작위 salt/nonce, 잘못된 비밀번호·tag/header/길이/파일 변조, oversized 입력의 KDF 전 차단, source 읽기 변경, 기존 대상 보존, private 경로, short write/fsync 오류, 불완전 복원 표식, 유효AEAD지만 잘못된 내부DB, WAL 원문 bytes 보존을 검사했다. inspect의 인증된 envelope 검사와 복원 파일의 전체DB검사를 구분한다. native SQLite deserialize는 구현에서 제거했다.

CLI는 합성 문구만 사용해 실제 Linux PTY에서도 seal/inspect/restore를 실행했다. 입력이 echo되지 않았고, 잘못된 문구는 출력 폴더를 만들지 않았으며, 올바른 복원은 전체 ledger검사를 통과했다. unit검사는 non-TTY, getpass 경고, 재입력 불일치, 비밀번호 인수를 잘못 제공했을 때 값이 오류에 노출되지 않는 경우를 포함한다. 실제 사용자의 비밀번호나 기업 데이터는 사용하지 않았다.

작은 합성12사례 측정(같은 Linux process, tools/measure_sealed.py): DB90,112bytes, sealed90,482bytes, seal0.3365s/inspect0.3363s/restore0.3478s, process peak RSS158,121,984bytes였다. 이는 한 번의 작은 sample 측정이며,128MiB최대파일·다른컴퓨터·동시부하의 성능 보장이 아니다. Windows와 실제 UI 측정은 docs/design/frontend-qa.md에 별도 기록한다.


### 0.7.0 Windows final validation

Windows Python 3.12.10 with the hash-locked optional encryption environment ran 170 tests: 165 passed and 5 skipped (two POSIX permission tests and three unavailable Windows symlink-privilege tests). Path and hardlink rejection remained separate and passed. Node 24.22.1 passed all 29 frontend tests; standard-library-only core import, pip check, validator (3 packs / 36 cases), demo, offline workbench, syntax, compileall and whitespace checks passed. Installed Chrome passed the full workbench regression, 10 archive groups, 7 recovery groups and 7 encrypted-copy recovery groups. Actual desktop/mobile screenshots were opened and inspected. The 12-case measurement and limits are recorded in `docs/design/frontend-qa.md`. This does not claim Windows hidden-input terminal execution, maximum-size performance, Windows ACL isolation or production readiness. Exact-commit CI is checked separately across eight Ubuntu/Windows Python versions.


### Reproducible CI runner scope (2026-11-08)

The current CI matrix explicitly uses `ubuntu-24.04` and `windows-latest`, with all four CPython versions 3.10, 3.11, 3.12 and 3.13 on each runner (eight jobs). No test was removed, disabled or newly skipped for this runner selection. During release verification, the moving `ubuntu-latest` label selected Ubuntu 26.04.1; its official Python 3.10.22 download returned HTTP 504 through the setup action retries and one failed-job rerun, before application tests could execute. The official same-release Ubuntu 24.04 x64 asset was confirmed present. Linux CI is pinned to Ubuntu 24.04 for a reproducible test target; this is an infrastructure/environment selection, not an application defect fix or a claim of Ubuntu 26.04 support. Exact-commit CI results remain the release gate.
