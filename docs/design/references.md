# 설계 참고와 구현 경계

공식 공개 문서의 사례별 비교, 실행 추적, 기준 실행 비교 원칙을 설계 참고로 삼았다. 코드·화면·자산을 가져오지 않고 AX의 정책·FAQ·API·독립 상태 검증에 맞춰 별도로 구현했다. 성능이나 완성도가 이 제품들과 동등하다고 주장하지 않는다.

- [Promptfoo Web Viewer](https://www.promptfoo.dev/docs/usage/web-ui/): 사례별 후보 출력 비교, 실패·오류·상이 필터, 셀 상세. AX에서는 사례를 행으로, FAQ/API 검사를 별도 열로 표시한다.
- [Langfuse Compare Experiments](https://langfuse.com/docs/evaluation/experiments/compare-experiments): 같은 평가 조건의 실행 비교와 사례별 개선·회귀 검토. AX에서는 범위·정책·입력·기대값·구현 근거가 일치할 때만 비교하며, 보류·누락은 통과로 바꾸지 않는다.
- [GoRules Test with Simulator](https://docs.gorules.io/learn/authoring/testing): 입력·출력·trace를 따라가는 실행 확인. AX에서는 기대값, 실제 FAQ/기준 API/후보 API 응답을 병렬로 보여 준다.
- [OpenL Editing & Testing](https://openl-tablets.github.io/openl-tablets/user-guides/openl-studio/editing-testing): 기대값 대 실제값과 규칙 실행 상세. AX에서는 결과 배지에서 원문 근거와 실제 관찰 자료로 이동한다.

독립 저장 상태의 대상·작업 키·입력·재호출 불변성 검증은 AX 자체 검증 설계다. 위 도구들의 해당 기능을 복제했다고 설명하지 않는다.

## 이번 범위에서 제외한 것
범용 규칙/노드 편집기, 임의 문서 의미 추출, 자동 영향 관계 확정, 운영 승인, 실제 서비스 연결, 다중 사용자·영속 이력은 구현하지 않았다. 정책 조항과 시나리오의 포괄적 커버리지도 아직 주장하지 않는다. 외부 소스 재사용을 도입한다면 해당 버전의 라이선스와 고지 의무를 별도로 확인해야 한다.
