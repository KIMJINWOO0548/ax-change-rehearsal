# 가상 반품 기간 변경 — policy_after.md

독자 작성한 합성 시험 규정입니다. 실제 회사의 규정·금융 조건·안전 기준이 아닙니다.

한국 내 주문만 지원한다. 필수 입력 누락/null은 NEEDS_INPUT, elapsed_days 음수·비정수·잘못된 날짜·opened/custom_made가 boolean이 아닌 경우는 INVALID_INPUT이다. 필수값 및 형식 확인 후 다른 지역은 UNSUPPORTED다. 개봉 또는 주문제작이면 기간과 관계없이 INELIGIBLE이다. 그 외 입력에서 elapsed_days가 허용 기간 이하이면 ELIGIBLE, 초과하면 INELIGIBLE이다. 마지막 날을 포함한다. elapsed_days는 이미 계산된 정수 일수로 주어지며 배송일로 일수를 계산하는 기능은 이 합성 계약 밖이다. ELIGIBLE이면 해당 주문에 모의 반품 접수를 한 건 만들고 같은 operation_key의 반복은 추가 생성하지 않는다. 다른 상태에서는 쓰기가 없다.

delivered_on이 2026-12-01 이후이면 허용 기간은 30일, 그 이전 배송 건은 14일이다. 시행일 당일 배송을 포함한다.
