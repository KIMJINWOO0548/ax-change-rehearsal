"""Escaped, self-contained HTML. No scripts, external assets or active URLs."""
from __future__ import annotations

import html
import json


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def block(value) -> str:
    return '<pre>' + esc(json.dumps(value, ensure_ascii=False, indent=2)) + '</pre>'


def badge(value) -> str:
    kind = 'bad' if value in {'FAIL', 'BLOCKED'} else ('warn' if value in {'INCONCLUSIVE', 'REVIEW_REQUIRED'} else 'ok')
    return f'<span class="badge {kind}">{esc(value)}</span>'


def render_html(report: dict) -> str:
    sections = []
    for stage in report['stages']:
        total = len(stage['cases'])
        counters = ''.join(f'<div class="metric"><b>{stage["counts"].get(key, 0)} / {total}</b><span>{label}</span></div>' for key, label in [('PASS_WITHIN_SCOPE', '등록 사례 통과'), ('FAIL', '불일치'), ('INCONCLUSIVE', '미확인')])
        rows = []
        for api, faq, merged in zip(stage['api']['cases'], stage['faq']['cases'], stage['cases']):
            sides = ''.join('<div><h4>' + name + '</h4>' + block(api[side]) + '</div>' for side, name in [('baseline', '기준 API: 응답·기대·관찰 상태'), ('candidate', '후보 API: 응답·기대·관찰 상태')])
            rows.append('<details><summary>' + badge(merged['business_verdict']) + ' ' + esc(api['id']) + ' · ' + esc(api['label']) + '</summary><div class="case"><p>의도: ' + esc(api['intended_behavior']) + ' · 합성 입력 / 실제 모의 실행 관찰</p><h4>입력</h4>' + block(api['input']) + '<div class="columns">' + sides + '</div><h4>FAQ: 독립 기대값과 실제 응답</h4>' + block(faq) + '</div></details>')
        sections.append('<section><h2>' + esc(stage['title']) + '</h2>' + badge(stage['readiness']) + '<div class="metrics">' + counters + '</div><p>FAQ 업무 판정: ' + esc(stage['faq']['counts']) + '<br>API 업무 판정: ' + esc(stage['api']['counts']) + '</p><div class="faq"><strong>설정에서 생성된 FAQ</strong><p>' + esc(stage['faq']['text']) + '</p><p>검토 hash 일치: ' + esc(stage['faq']['review_valid']) + '<br>FAQ SHA-256: ' + esc(stage['faq']['sha256']) + '<br>실행 manifest: ' + esc(stage['manifest_sha256']) + '</p></div><details><summary>고정된 설정·검토·API manifest</summary>' + block({'faq_config': stage['faq']['content'], 'review': stage['faq']['review'], 'api_manifest': stage['api']['manifest']}) + '</details><h3>사례별 근거 · 펼쳐서 전후 상태 확인</h3>' + ''.join(rows) + '</section>')
    evidence = ''.join('<article><h3>' + esc(side) + '</h3><p>' + esc(item['path']) + '</p><pre>' + esc(item['text']) + '</pre><p>SHA-256: ' + esc(item['sha256']) + '</p></article>' for side, item in report['evidence'].items())
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>반품 정책 변경 리허설</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#edf2f6;color:#172b42;font:15px/1.65 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:32px 24px 70px}header{padding:42px;background:#122b44;border-radius:20px;color:#fff}header p{color:#c9d8e8}h1{font-size:clamp(26px,4vw,40px);line-height:1.3;margin:12px 0}h2{font-size:24px}section{background:#fff;border:1px solid #d9e2ec;border-radius:16px;padding:28px;margin:24px 0}.eyebrow{letter-spacing:.12em;color:#8edbcb;font-size:12px;font-weight:700}.badge{display:inline-block;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:700}.bad{background:#fbe4e8;color:#a32038}.warn{background:#fff0cc;color:#785100}.ok{background:#dff5ec;color:#0c684a}.metrics,.columns{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:20px 0}.columns{grid-template-columns:repeat(2,minmax(0,1fr))}.metric{background:#f2f5f9;padding:18px;border-radius:10px}.metric b{display:block;font-size:27px}.metric span{color:#5d7086}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.65 ui-monospace,monospace;background:#f1f5f8;border-radius:8px;padding:16px}p{overflow-wrap:anywhere}details{border-top:1px solid #e2e8ee;padding:12px 0}summary{cursor:pointer;font-weight:600}.case{padding:10px 0}.faq{border-left:4px solid #248e7d;background:#eff8f6;padding:12px 20px;margin:20px 0}.faq p:last-child{font-size:12px;color:#456457}li{margin:8px 0}footer{color:#5d7086}@media(max-width:700px){main{padding:16px}header,section{padding:22px}.columns,.metrics{grid-template-columns:1fr}}@media print{body{background:white}section,header{break-inside:avoid}}
</style></head><body><main><header><div class="eyebrow">AX CHANGE REHEARSAL · OFFLINE DEMO</div><h1>''' + esc(report['title']) + '''</h1><p>문서만 고쳐서는 끝나지 않습니다. 같은 입력을 실행하고, 실제 모의 접수 상태까지 확인합니다.</p><p>합성 자료 전용 · Python 표준 라이브러리 · LLM 미실행 · 외부 시스템 미연결</p></header><section><h2>변경 근거와 범위</h2><p>2026-12-01 이후 배송된 한국 미개봉 일반 상품. 이전 배송과 개봉·주문제작 예외는 유지합니다. 각 단계는 별도의 격리된 메모리 실행이며 실제 외부 API를 변경하지 않습니다.</p><div class="columns">''' + evidence + '</div><p>기대값 출처: ' + esc(report['oracle_provenance']) + ' · 전문가 검증: ' + esc(report['expert_reviewed']) + '</p></section>' + ''.join(sections) + '<section><h2>미확인 범위와 다음 검토</h2><ul>' + ''.join('<li>' + esc(s) + '</li>' for s in report['unknowns']) + '</ul></section><footer>카운터는 저장된 실행 결과에서 계산됩니다. 진단 assertion 통과와 업무 판정 통과는 구분합니다. 상세 기록은 함께 생성된 JSON에서 확인할 수 있습니다.</footer></main></body></html>'
