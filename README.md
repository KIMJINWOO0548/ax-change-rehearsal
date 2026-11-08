# AX Change Rehearsal

**업무 규정이 바뀌었을 때, FAQ와 업무 프로그램에 같은 변경이 반영됐는지 실행으로 확인하는 로컬 리허설 도구입니다.**

고객서비스의 반품 기간 **14일 → 30일** 변경을 예로, FAQ만 수정한 상태와 API까지 수정한 상태를 구분합니다. 응답뿐 아니라 별도로 조회한 모의 저장 상태까지 비교합니다.

현재 버전은 **합성 데이터와 메모리 기반 모의 어댑터를 사용하는 통제된 로컬 파일럿 기반**입니다. 선택적으로 실행 근거와 검토 메모를 로컬에 보관합니다. 실제 고객 데이터, 외부 기업 API, LLM, 문서 의미 추출, 운영 배포는 포함하지 않습니다.

## 빠른 시작

기본 작업대·평문 백업은 Python 3.10 이상이며 추가 패키지·API 키가 필요 없습니다. 선택적 암호화 기능은 별도 고정 의존성을 설치합니다.

```bash
git clone https://github.com/KIMJINWOO0548/ax-change-rehearsal.git
cd ax-change-rehearsal
python -m unittest discover -s tests -v
python serve_workbench.py
```

브라우저에서 **http://127.0.0.1:8765** 를 엽니다. 정책 원문과 변경된 줄을 확인하고, FAQ/API 버전을 각각 선택한 뒤 실제 리허설을 실행하세요. 사례별 응답·접수 상태·정책 근거와 원시 JSON을 확인할 수 있습니다. 설정을 바꾸면 이전 결과는 다시 실행하기 전까지 현재 결과로 표시되지 않습니다.

### 작업 흐름

1. **변경 확인:** 14일에서 30일로 바뀐 조항과 유지되는 조건을 확인합니다. 전체 원문과 hash를 펼칠 수 있습니다.
2. **사례 선택:** 검색·개별 선택·경계값·예외·보류 입력으로 실행 범위를 정합니다. 검색은 선택을 바꾸지 않습니다.
3. **리허설 실행:** 등록된 FAQ/API 모의 버전을 각각 선택합니다. 선택한 사례만 실제 실행하며 제외된 사례는 검증하지 않습니다.
4. **차이·근거 검토:** 기대값·FAQ·기준/후보 API 응답과 독립 관찰 상태를 읽고, 실패 사례만 선택해 다시 검증합니다.

최근 8개 실행을 이 탭의 메모리에 보관합니다. 같은 범위·정책·입력·기대값·구현 버전끼리 업무 개선/회귀와 FAQ/API 검사 개선/회귀를 비교합니다. 이 비교 이력은 새로고침하면 사라집니다. 별도 로컬 기록을 켜면 실행 원본과 검토 메모를 계속 보관할 수 있습니다. 부분 실행이 통과해도 전체 범위가 통과한 것은 아닙니다.

### 선택적 로컬 기록

```bash
python serve_workbench.py --workspace /absolute/private/location/ax-pilot
python manage_evidence.py --workspace /absolute/private/location/ax-pilot verify
python manage_evidence.py --workspace /absolute/private/location/ax-pilot list
python manage_evidence.py --workspace /absolute/private/location/ax-pilot replay RUN_ID
```

본인만 접근할 수 있는 위치의 새 폴더를 소스 저장소 밖에 지정하세요. 저장된 원본 결과, scope, hash, 검토 이력을 다시 열 수 있습니다. 검토 메모는 실행 hash·revision에 묶이며 다른 탭의 변경을 덮어쓰지 않습니다. 무결성 검사가 실패하면 중지하고, 동일 합성 결과의 명시적 재현은 원본/검토 상태를 바꾸지 않습니다. 최대 100회 실행을 저장하며 자동 삭제하지 않습니다.

**이 기록은 암호화·사용자 인증·변경 불가능한 감사 로그가 아닙니다. 검토 표식은 배포 승인이 아닙니다.** 실제 고객·직원 정보나 비밀은 입력하지 마세요. 안전한 실행·백업·실제 기업 파일럿 전 수용 조건은 [LOCAL_PILOT.md](docs/LOCAL_PILOT.md)에 있습니다.

### 검증 가능한 백업·복원

```bash
python manage_recovery.py backup --workspace /private/ax-pilot --destination /private/ax-backup-001
python manage_recovery.py inspect --source /private/ax-backup-001
python manage_recovery.py restore --source /private/ax-backup-001 --destination /private/ax-restored-001
```

백업과 복원은 새 전용 폴더에만 수행하며 기존 데이터는 덮어쓰지 않습니다. SQLite snapshot, 파일 checksum, schema와 ledger를 확인한 뒤 복원합니다. 백업도 평문이며 인증된 감사나 암호화가 아닙니다. 복원된 기록을 실제 승인으로 바꾸지 않습니다. [복구 훈련과 한계](docs/RECOVERY.md)를 먼저 확인하세요.

### 선택적 암호화 사본

```bash
python -m pip install --require-hashes --only-binary=:all: -r requirements-encryption.txt
python manage_sealed.py seal --source /private/ax-backup-001 --destination /private/ax-backup-001.axsealed
python manage_sealed.py inspect --source /private/ax-backup-001.axsealed
python manage_sealed.py restore --source /private/ax-backup-001.axsealed --destination /private/ax-restored-002
```

검증된 cryptography의 AES-256-GCM과 고정 scrypt로 **새 사본만** 암호화합니다. 비밀번호는 로컬 터미널에서 숨겨 입력하며 채팅·명령줄·환경변수·파일로 받거나 저장하지 않습니다. 암호문/내부 checksum 검사와 복원 후 전체 DB 검증을 구분합니다. 원본 DB·평문 백업·복원된 공간은 계속 평문이며, 비밀번호 분실 복구나 조직 키 관리는 제공하지 않습니다. [사용·복구 경계](docs/SEALED_BACKUPS.md)와 [의존성 검토](docs/DEPENDENCIES.md)를 먼저 확인하세요.

이 서버는 로컬 컴퓨터의 합성 검증용입니다. 외부 네트워크에 공개하거나 운영 서버로 사용하지 마세요. 종료는 Ctrl+C입니다. 다른 포트는 `python serve_workbench.py --port 8766`으로 지정할 수 있습니다.

서버 없이 읽는 오프라인 보고서도 지원합니다.

```bash
python tools/validate_package.py
python run_demo.py
python run_workbench.py
```

`results/workbench/index.html`을 브라우저에서 열면 정적 3단계 보고서를 볼 수 있습니다. 원시 근거는 `workbench.json`에 저장됩니다. `run_demo.py`는 제조·금융·고객서비스 전체와 결함 주입 회귀를 실행합니다.

## 데모에서 확인할 것

| 단계 | 실제 실행 결과 | 의미 |
|---|---|---|
| FAQ·API가 모두 이전 기준 | 12개 중 불일치 4개 | 새 정책의 반영 누락 |
| FAQ만 수정 | 12개 중 불일치 4개 | 설명을 고쳐도 실제 처리 오류는 남음 |
| FAQ·API 모두 수정 | 불일치 0개, 통과 9개, 미확인 3개 | 결측·오류·지원 범위 밖은 여전히 보류 |

이는 동봉한 합성 사례의 결과이며 실제 업무 정확도나 고객 도입 성과가 아닙니다. 상세 재현 방법은 [WORKBENCH.md](docs/WORKBENCH.md)를 참고하세요.

## 안전하게 실패하는 검증

- 빈 팩, 중복 시나리오·JSON 키, 잘못된 메타데이터와 경로 이탈을 실행 전에 거부합니다.
- 호출 timeout 뒤에도 저장 상태를 확인합니다. 결과가 불확실한 요청을 자동 재호출하지 않습니다.
- 같은 작업 키·같은 입력은 멱등 처리하고, 같은 키·다른 입력은 충돌로 거부합니다.
- 기대값은 검증기만 읽으며 업무 어댑터에는 전달하지 않습니다.
- 진단 assertion 통과와 업무 판단 통과를 구분합니다.
- FAQ 설정이 바뀌면 이전 검토 hash가 무효화됩니다. 이는 데모용 검토 표식이며 사용자 인증·전자서명이 아닙니다.

## 구조

- `web/`: 정책 비교, 실행 설정, 사례별 근거와 JSON 내려받기를 제공하는 실제 작업 화면.
- `rehearsal/app.py`, `server.py`: 고정된 정책 검토와 실제 모의 실행을 연결하는 로컬 HTTP API.
- `rehearsal/sealed.py`, `manage_sealed.py`: 선택적 암호화 사본·숨김 비밀번호 입력·복원 검증.
- `rehearsal/storage.py`, `replay.py`, `recovery.py`: 선택적 로컬 실행/검토 기록, 무결성 검사, 명시적 합성 재현과 검증 가능한 백업·복원.
- `rehearsal/engine.py`: 전후 실행, 재호출 검사, 독립 상태 관찰, 판정.
- `rehearsal/validation.py`: 구현된 합성 팩의 엄격한 입력 계약 검사.
- `rehearsal/adapters.py`: 세 업종의 모의 업무 규칙과 10가지 오류 주입.
- `rehearsal/workbench.py`, `report.py`: FAQ/API 재검증과 오프라인 HTML.
- `fixtures/`: 합성 규정 6개와 독립 작성한 시나리오 36개.
- `examples/customer_service/`: 편집 가능한 FAQ 설정과 검토 hash.
- `tests/`: 정상·변형·오류 경계·상태·보고서 자동 회귀.
- `contracts/`: 데이터 계약과 스키마.
- `PROJECT_PLAN.md`, `TASKS.md`: 향후 설계와 미완료 범위.
- `.github/workflows/ci.yml`: Python 버전별 테스트와 데모 재생성.

## 제한과 다음 단계

현재 정책 시행일은 `2026-12-01`이며 모의 어댑터가 구현한 규정에 한정됩니다. 임의의 새 시행일을 메타데이터만 바꿔 실행할 수 없습니다. 날짜별 정책을 확장하려면 어댑터·규정·독립 시나리오를 함께 검토해야 합니다.

메모리 분리는 OS 보안 샌드박스가 아닙니다. 실제 API/DB 연결, 중단 작업 추적·worker 재개, 사용자 인증·권한, 문서 파싱·의미 추출, 현업 정답 검증은 아직 구현하지 않았습니다. 정책 근거 위치는 수동 등록했으며 원문 hash가 바뀌면 작업대 실행을 막습니다. 로컬 요청 토큰은 다른 웹사이트의 요청을 차단하기 위한 장치이며 사용자 인증을 대신하지 않습니다. 실행 도중 소스를 수정하면 차단하므로 업그레이드 후 서버를 다시 시작해야 합니다. 설계 참고는 [references.md](docs/design/references.md), 실제 UI 검증 범위는 [frontend-qa.md](docs/design/frontend-qa.md)에 있습니다. 자세한 상태는 [HANDOFF.md](HANDOFF.md), 검증 범위는 [VALIDATION.md](docs/VALIDATION.md)에 있습니다.

## 공개 범위와 라이선스

이 저장소에는 합성 예시와 프로젝트 소스만 포함합니다. 원본 업로드 ZIP, 로컬 경로·인증정보·개인 연락처는 포함하지 않습니다. 원본 패키지에 재사용 라이선스가 없으므로 임의로 오픈소스 라이선스를 추가하지 않았습니다. 공개 열람과 소스 재사용 허가는 다르며, 재사용 조건은 저장소 소유자에게 확인해야 합니다.
