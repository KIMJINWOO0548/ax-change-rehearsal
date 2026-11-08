# 고객서비스 변경 리허설 작업대

외부 연결 없이 Python 표준 라이브러리만으로 재현하는 **합성 데모**입니다. 실제 기업 도입, 실제 고객 처리, AI 실행, 전문가 정책 검토를 의미하지 않습니다.

## 실행

저장소 루트에서 Python 3.10 이상으로 실행합니다.

```sh
python -m unittest discover -s tests -p 'test_workbench.py' -v
python run_workbench.py
```

생성된 `results/workbench/index.html`을 브라우저에서 파일로 엽니다. 서버나 인터넷 연결이 필요 없습니다. 상세 기록은 같은 폴더의 `workbench.json`에 저장됩니다. 파일을 다시 생성하면 해당 출력 파일만 덮어씁니다. 다른 출력 폴더는 `--output /tmp/ax-workbench`로 지정합니다.

## 시연 순서

1. 정책은 14일에서 30일로 바뀌었으나 FAQ와 API가 옛 기준을 사용하는 단계를 봅니다.
2. FAQ 설정만 수정해도 API의 접수 거절과 상태 불일치는 남아 있음을 확인합니다.
3. API까지 수정한 후보를 새로 실행합니다. S04의 후보 API 관찰 상태가 빈 목록에서 접수 한 건으로 달라집니다.
4. 기존 배송, 개봉, 주문제작, 경계 사례를 펼쳐 회귀 여부를 확인합니다.
5. 미확인 사례와 업무 판단을 구분합니다. 모든 진단 assertion이 통과하더라도 최종 상태는 미확인 입력·지원 범위 때문에 REVIEW_REQUIRED일 수 있습니다.

각 단계의 API는 `engine.run_pack`을 실제 호출합니다. 앞 두 단계는 `stale_candidate`, 마지막은 `normal`입니다. 각 사례와 단계는 격리된 메모리 환경을 새로 만듭니다. 실제 프로그램을 패치하거나 외부 API를 호출한 것은 아닙니다. 같은 키의 재호출과 별도 상태 관찰은 엔진에서 수행합니다.

## FAQ 설정과 검토

`examples/customer_service/faq_stale.json`과 `faq_corrected.json`의 `content`가 사람이 편집하는 구조화된 설정입니다. FAQ 문장은 이 설정에서 생성되며 임의 문서에서 자동 추출하지 않습니다. 개봉·주문제작 제외와 마지막 허용일 포함은 이 제한된 FAQ 실행기의 고정 동작입니다.

- FAQ 실행기에는 업무 입력과 FAQ 설정만 전달합니다.
- 기대값은 별도 작성된 `fixtures/customer_service/pack.json`에서 평가기가 읽습니다. FAQ 설정을 고쳐도 기대값은 바뀌지 않습니다.
- `content`가 바뀌면 SHA-256이 바뀌고 기존 검토는 무효가 됩니다. 재검토하지 않은 설정은 실행하지 않고 INCONCLUSIVE로 남깁니다.
- 검토 기록은 로컬 합성 시연용 선언입니다. 인증된 승인 서비스나 서명, 실제 전문가 검토를 구현한 것은 아닙니다.

수정된 내용을 직접 검토한 후에만 해당 파일의 `review.content_sha256`을 새 hash로 바꿉니다. 예를 들어 아래 명령은 hash를 출력할 뿐 파일을 승인하거나 수정하지 않습니다.

```sh
python -c "from pathlib import Path; from rehearsal.workbench import load_faq; from rehearsal.adapters import digest; print(digest(load_faq(Path('examples/customer_service/faq_corrected.json'))['content']))"
```

다른 파일을 시험하려면 `python run_workbench.py --corrected-faq /path/to/faq.json --output /tmp/ax-edited`를 실행합니다. 검토 hash가 유효하더라도 잘못된 설정은 독립 기대값 비교에서 실패합니다. JSON 문법 오류나 필수 최상위 구조 누락은 입력 파일 오류로 CLI 실행이 중단될 수 있습니다.

## 근거와 보안 범위

보고서에는 전후 정책 원문·hash, FAQ 내용·검토 hash, API manifest, 시나리오 입력, 독립 기대값, 응답, 전후 상태, assertion 오류가 포함됩니다. 작업대 소스 파일 hash도 JSON과 실행 manifest에 묶습니다. 숫자는 실행 사례에서 계산하며 하드코딩한 성공 카운터는 없습니다.

HTML은 사용자 문자열을 escape하고 실행 스크립트·원격 의존성을 넣지 않습니다. 제한적인 Content Security Policy를 포함합니다. 접기/펼치기는 브라우저의 기본 `details` 요소입니다. 원시 JSON도 같은 폴더에서 직접 확인할 수 있습니다.

실제 연동, 임의 문서 의미 검증, LLM/RAG, 접근 제어, 지속형 승인, 비용·성능 측정과 운영 배포는 아직 범위 밖입니다. 이 HTML은 **오프라인 실행 보고서**이며 실시간 편집 웹앱이나 공개 배포 서비스가 아닙니다.
