# 가상 점검 주기 변경 — policy_before.md

독자 작성한 합성 시험 규정입니다. 실제 회사의 규정·금융 조건·안전 기준이 아닙니다.

한국 사업장의 가상 장비군 A/B만 지원한다. mode는 normal 또는 special이다. 필수 입력 누락/null은 NEEDS_INPUT, 시간의 음수·비정수·잘못된 날짜 형식은 INVALID_INPUT이다. 그 외 지역·장비군·운전유형은 UNSUPPORTED다. 필수값 및 형식 확인 후 지원 범위를 확인한다. 판정 기준일은 assessment_date다. hours_since_inspection은 정수 누적 운전시간이며 기준 이상이면 DUE, 미만이면 NOT_DUE다. DUE일 때 해당 장비에 모의 점검 작업 한 건을 만들고 같은 operation_key의 반복은 추가 생성하지 않는다. 그 외 상태에서는 쓰기가 없다. 실장비를 제어하지 않는다. 장비군 B는 운전유형과 관계없이 120시간, 장비군 A의 special은 60시간이다.

장비군 A의 normal은 모든 판정일에 100시간 기준을 사용한다.
