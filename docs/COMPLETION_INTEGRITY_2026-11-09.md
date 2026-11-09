# 오프라인 실행 범위와 재현 증거 무결성

2026-11-09 UTC. 접근 가능한 원격 개선 브랜치
`feature/ui-review-workspace-v08-public`의
`a0152c22c32c09ad9bdb90bec759d8fa3ec4fe87`에서 독립 구현했다.
새 브랜치는 `improve/run-completion-integrity-20261109`다. 접근 제한된
기존 보존본은 읽거나 복원하지 않았으며 해당 작업과 별도 이력이다.

## 수정한 경계

오프라인 `build_workbench()`는 API와 FAQ 결과를 `zip()`으로 합쳤다.
한쪽 사례가 빠지면 누락을 조용히 제외했고, 빈 FAQ 결과를 주입하면
세 단계 모두 0건·빈 counts인데 `PASS_WITHIN_REGISTERED_SCOPE`를 반환했다.
알 수 없는 업무 판정도 FAIL/INCONCLUSIVE가 아니라는 이유로 통과가 될 수 있었다.
이는 하위 평가기 오류를 주입해 확인한 통합 경계이며, 현재 정상 평가기에서
같은 누락이 자연 발생했다고 주장하지 않는다.

이제 결과 목록이 등록 사례의 ID·개수·순서와 정확히 같고 모든 업무 판정이
선언된 세 값 중 하나여야 통합한다. 누락·빈 목록·중복·순서 오류·미등록 ID·
잘못된 목록/판정은 고정 ValueError로 거부한다. 보고서 생성은 집계 전에
중단되며, CLI도 출력 폴더를 생성하기 전에 실패한다.

`replay_report()`의 Python 값 비교에는 `True == 1 == 1.0` 경계가 있었다.
정수 건수를 같은 값의 불리언/실수로 바꿔도 MATCH가 될 수 있었다. 이제
기존 canonical JSON 표현으로 설정·scope·manifest·각 증거 섹션을 비교한다.
키 순서는 무시하되 숫자 표현과 불리언을 구분하며, 없는 섹션과 명시적 null도
구분한다. 문맥 불일치는 실행 전에 거부하고, manifest 변경은 INCOMPATIBLE,
증거 변경은 DIFFERENT로 남긴다.

MATCH는 같은 합성 증거를 재현했다는 뜻이다. 부분 범위·INCONCLUSIVE 결과도
그대로 재현하면 MATCH일 수 있으며 이를 업무 통과·전체 완료·배포 승인으로
바꾸지 않는다. `deployment_approval`은 계속 false다. 저장 원장/schema와
기존 metadata-only 요약 형식은 변경하지 않았다.

## 실제 검증

Linux / Python 3.12.14. 이번 증분에서 새 패키지나 전역 설정을 설치·변경하지 않았다.

| 검사 | 관찰 결과 |
| --- | --- |
| 접근 가능한 기준 코드 | Python unittest 170개 통과 |
| 독립 초기 RED | 새 7개 method, 실패 18건·오류 2건. 두 오류는 기존 잘못된 목록의 TypeError 경계 |
| 확장된 정확한 기준 코드 RED | 7개 method, 실패 24건·오류 2건 |
| 초기 영향 범위 GREEN | 49개 method 통과 |
| null/누락 섹션 회귀 | 별도 1개 method가 먼저 실패한 뒤 수정 |
| 최종 전체 회귀 | 178개 method 통과, 실패·skip 없음 |
| 프런트엔드 상태 | 기존 Node 시험 32개 통과; 새 브라우저 실행과 구분 |
| 보조 검사 | 표준 라이브러리 전용 import, 패키지/fixture 검사, JS 3개 구문 검사, compileall 통과 |
| 전체 모의 CLI | 11개 variant × 36개 사례 실행. 정상은 업무 통과 27·미확인 9, observer_timeout은 36개 모두 INCOMPLETE/INCONCLUSIVE |
| 내부 읽기 검토 | 두 내부 에이전트가 코드/시험 검토. 외부 사람·현업 검토가 아님 |

확장 RED를 위한 첫 임시 기준 코드 복사에는 공개 `run_workbench.py`가 빠져
FileNotFoundError가 섞였다. 이 실행은 동작 RED 건수에서 제외하고 실패 기록을
보존했다. 누락 파일을 포함한 새 임시 복사에서 위의 24건·2건을 확인했다.
기존 원본 작업대에서 얻은 초기 RED와 최종 GREEN은 이 복사 오류와 별개다.

실제 `run_workbench.py` 합성 CLI의 세 단계는 각각 등록 사례 12개이며
FAIL 4/4/0, INCONCLUSIVE 3/3/3을 보존했다. 준비 상태는
BLOCKED/BLOCKED/REVIEW_REQUIRED다. 누락 FAQ 결과를 메모리로 주입한
CLI 경로는 출력 폴더 없이 거부됐다. 두 실제 로컬 저장/replay CLI는
PARTIAL_SCOPE와 REVIEW_REQUIRED를 보존하고 원본 report·review 기록을
변경하지 않았다. 모든 시험 입력은 동봉 합성 자료다.

집계·명령·해시·검사 결과는
[verification.json](evidence/completion-integrity-20261109/verification.json)에 있다.
원시 로컬 로그는 `/tmp/ax-rehearsal-20261109T163205Z-24b98b40-completion/`에
보존하며 정책 입력·검토 메모·로컬 DB·암호화 사본은 공개 근거에 포함하지 않는다.
커밋/푸시·원격 SHA와 CI 관찰은 커밋 뒤 별도 기록한다.

## 범위와 미검증

UI·렌더링 템플릿·모의 업무 규칙·기대 정답·fixture는 변경하지 않았다.
실행 상태/worker 재개·외부 효과 복구·실제 기업 API·사용자 인증·배포 승인·
전체 저장 내용의 의미 검증이나 서명 인증을 새로 구현한 변경은 아니다.
새 브라우저, Windows, 다른 Python 버전과 실제 기업 연동은 실행하지 않았다.
합성 재현과 로컬 해시 검사를 현업 정확도·실제 도입 효과로 해석하지 않는다.
