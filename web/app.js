/* Local-only workbench. All verdicts and evidence come from the server. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = { context: null, result: null, busy: false, revision: 0, request: 0, selected: null, stale: false };
  const verdicts = { PASS_WITHIN_SCOPE: '범위 내 통과', FAIL: '불일치', INCONCLUSIVE: '판정 보류', PASS: '통과', INCOMPLETE: '불완전' };
  const label = (value) => verdicts[value] || String(value ?? '제공되지 않음');
  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function badge(value) { return el('span', label(value), 'badge ' + (['PASS', 'PASS_WITHIN_SCOPE'].includes(value) ? 'pass' : value === 'FAIL' ? 'fail' : 'unknown')); }
  function configuration() { return { faq_version: document.querySelector('input[name="faq_version"]:checked').value, api_version: document.querySelector('input[name="api_version"]:checked').value }; }
  function status(text, kind = '') { $('run-status').textContent = text; $('run-status').className = 'notice ' + kind; }
  function availability() {
    const disabled = !state.context || state.context.policy_review_valid === false || state.busy;
    $('run').disabled = disabled;
    $('faq-field').disabled = disabled;
    $('api-field').disabled = disabled;
    $('run').textContent = state.busy ? '실행 중…' : state.result ? '다시 리허설 실행' : '리허설 실행';
    $('download').disabled = !state.result || state.stale || state.busy;
    $('results').setAttribute('aria-busy', String(state.busy));
  }
  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(path, { ...options, signal: controller.signal, credentials: 'same-origin', cache: 'no-store' });
      let data;
      try { data = await response.json(); } catch { throw new Error('서버가 올바른 JSON 응답을 보내지 않았습니다.'); }
      if (!response.ok) throw new Error(data.error?.message || `서버 요청 실패 (${response.status})`);
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('요청 시간이 초과됐습니다. 서버 상태를 확인하고 다시 실행하세요.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function renderPolicy(key) {
    const source = state.context.policy[key];
    const counterpart = state.context.policy[key === 'before' ? 'after' : 'before'];
    const lines = $(key + '-lines'); lines.replaceChildren();
    const other = new Set(counterpart.lines.map((line) => line.text));
    for (const line of source.lines) {
      const row = el('div', undefined, 'line' + (line.text && !other.has(line.text) ? ' changed' : ''));
      row.append(el('span', line.number, 'line-number'), el('span', line.text || ' ', 'line-text')); lines.append(row);
    }
    $(key + '-source').textContent = source.path + '\nSHA-256 ' + source.sha256;
  }
  async function loadContext() {
    $('reload').hidden = true; $('connection').hidden = false;
    $('connection').textContent = '정책과 시나리오를 불러오는 중입니다.';
    try {
      const context = await request('/api/context');
      if (!context.csrf_token || !context.policy?.before?.lines || !context.policy?.after?.lines || !context.defaults || !context.project) throw new Error('정책 응답의 필수 정보가 없습니다.');
      state.context = context;
      for (const name of ['faq_version', 'api_version']) {
        const input = Array.from(document.querySelectorAll(`input[name="${name}"]`)).find((item) => item.value === context.defaults[name]);
        if (!input) throw new Error('지원되지 않는 기본 버전입니다.'); input.checked = true;
      }
      renderPolicy('before'); renderPolicy('after');
      $('effective-date').textContent = `시행일 ${context.change.effective_date}`;
      $('before-days').textContent = `${context.change.old_window_days}일 기준`;
      $('after-days').textContent = `${context.change.new_window_days}일 기준`;
      document.querySelectorAll('.stale-label').forEach((node) => { node.textContent = `이전 정책 · ${context.change.old_window_days}일`; });
      document.querySelectorAll('.corrected-label').forEach((node) => { node.textContent = `변경 반영 · ${context.change.new_window_days}일`; });
      $('preserved').textContent = '유지되는 조건 · ' + context.change.preserved.join(' · ');
      $('scenario-count').textContent = `등록된 ${context.project.scenario_count}개 시나리오 · 모의 실행`;
      renderLimits(context.limits); $('connection').hidden = true;
      if (context.policy_review_valid === false) status('정책 문서가 바뀌었습니다. 근거와 독립 시나리오를 다시 검토해야 실행할 수 있습니다.', 'error');
    } catch (error) {
      state.context = null; $('connection').textContent = '연결하지 못했습니다. ' + error.message; $('connection').className = 'notice error'; $('reload').hidden = false;
    } finally { availability(); }
  }
  function renderLimits(limits) { $('limits').replaceChildren(...(limits || []).map((item) => el('li', item))); }
  function raw(title, value, open = false) {
    const details = el('details', undefined, 'raw-object'); details.open = open;
    details.append(el('summary', title), el('pre', JSON.stringify(value ?? null, null, 2))); return details;
  }
  function showDetail(item, focus = true) {
    state.selected = item.id;
    $('detail-title').textContent = item.label + ' · ' + item.id;
    $('detail-reason').textContent = item.reason || '서버가 별도 판정 사유를 제공하지 않았습니다.';
    const facts = $('detail-facts'); facts.replaceChildren();
    for (const [title, value] of [['업무 판정', label(item.business_verdict)], ['검증 상태', label(item.assertion_status)], ['의도한 동작', item.intended_behavior]]) facts.append(el('dt', title), el('dd', value));
    $('detail-evidence').replaceChildren(el('h3', '정책 근거'));
    for (const evidence of item.evidence || []) {
      const block = el('div', undefined, 'evidence');
      block.append(el('p', evidence.quote), el('p', `${evidence.path}:${evidence.line}\nSHA-256 ${evidence.sha256}`, 'mono')); $('detail-evidence').append(block);
    }
    if (!item.evidence?.length) $('detail-evidence').append(el('p', '이 사례에 연결된 정책 근거가 없습니다.'));
    $('detail-objects').replaceChildren(raw('업무 입력', item.input), raw('FAQ 실제 응답과 검증', item.faq, true), raw('후보 API 실제 응답 · 상태 관찰', item.candidate, true), raw('기준 API 실제 응답 · 상태 관찰', item.baseline));
    $('case-detail').hidden = false; renderRows();
    if (focus) $('case-detail').focus();
  }
  function renderRows() {
    const filter = $('verdict-filter').value;
    const rows = state.result.cases.filter((item) => filter === 'all' || item.business_verdict === filter);
    $('case-rows').replaceChildren();
    for (const item of rows) {
      const row = el('tr', undefined, state.selected === item.id ? 'selected' : '');
      const name = el('td', item.label); name.append(el('span', item.id, 'case-id'));
      const verdict = el('td'); verdict.append(badge(item.business_verdict));
      const assertion = el('td'); assertion.append(badge(item.assertion_status));
      const action = el('td'); const button = el('button', '근거 보기', 'secondary');
      button.type = 'button'; button.setAttribute('aria-label', `${item.label} 근거 보기`); button.setAttribute('aria-controls', 'case-detail'); button.setAttribute('aria-expanded', String(state.selected === item.id));
      button.addEventListener('click', () => showDetail(item)); action.append(button); row.append(name, verdict, assertion, action); $('case-rows').append(row);
    }
    $('visible-count').textContent = `${rows.length} / ${state.result.cases.length}개 표시`;
    $('no-results').hidden = rows.length !== 0;
  }
  function renderResult() {
    const result = state.result;
    $('result-content').hidden = false; $('case-detail').hidden = true; state.selected = null;
    $('summary').replaceChildren();
    for (const [name, count] of [['전체 시나리오', result.total], ...Object.entries(result.counts).map(([name, count]) => [label(name), count])]) {
      const item = el('div', undefined, 'summary-item'); item.append(el('strong', count), el('span', name)); $('summary').append(item);
    }
    $('run-meta').textContent = `실행 ${result.run_id} · ${result.created_at}\nFAQ ${result.configuration.faq_version} / API ${result.configuration.api_version}\nManifest SHA-256 ${result.manifest_sha256}`;
    $('verdict-filter').replaceChildren(new Option('전체', 'all'), ...[...new Set(result.cases.map((item) => item.business_verdict))].map((value) => new Option(label(value), value)));
    renderLimits(result.limits); renderRows();
    const readiness = ({ BLOCKED: '불일치 수정 필요', REVIEW_REQUIRED: '보류 사례 검토 필요', PASS_WITHIN_REGISTERED_SCOPE: '등록 범위 내 통과' })[result.readiness] || String(result.readiness);
    status(`실행 완료 · ${readiness}. 아래 판정은 이 모의 실행의 범위에 한합니다.`, 'success');
  }
  async function run(event) {
    event.preventDefault();
    if (state.busy || !state.context || state.context.policy_review_valid === false) return;
    state.busy = true; const token = ++state.request; const revision = state.revision;
    const config = configuration(); availability(); status('실제 시나리오를 실행하고 응답과 상태를 확인하고 있습니다.');
    // A failed rerun must not leave the previous result looking current.
    if (state.result) state.stale = true;
    try {
      const result = await request('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': state.context.csrf_token }, body: JSON.stringify(config) });
      if (token !== state.request || revision !== state.revision) return;
      if (!Array.isArray(result.cases) || !result.counts || !Number.isInteger(result.total) || !result.run_id || result.configuration?.faq_version !== config.faq_version || result.configuration?.api_version !== config.api_version) throw new Error('실행 결과의 필수 정보 또는 설정이 일치하지 않습니다.');
      state.result = result; state.stale = false; renderResult();
    } catch (error) {
      if (token === state.request) status(`실행하지 못했습니다. ${error.message}${state.result ? ' 아래는 이전 실행 결과이며 현재 결과가 아닙니다.' : ''} 서버를 확인한 뒤 다시 실행하세요.`, 'error');
    } finally { if (token === state.request) { state.busy = false; availability(); } }
  }
  $('run-form').addEventListener('submit', run);
  $('run-form').addEventListener('change', () => {
    state.revision++;
    if (state.result) { state.stale = true; status('설정이 변경됐습니다. 아래는 이전 실행 결과입니다. 다시 실행해야 현재 설정의 판정을 확인할 수 있습니다.', 'warning'); }
    availability();
  });
  $('verdict-filter').addEventListener('change', () => { state.selected = null; $('case-detail').hidden = true; renderRows(); });
  $('close-detail').addEventListener('click', () => { state.selected = null; $('case-detail').hidden = true; renderRows(); $('verdict-filter').focus(); });
  $('download').addEventListener('click', () => {
    if (!state.result || state.stale || state.busy) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(state.result, null, 2)], { type: 'application/json' }));
    const link = el('a'); link.href = url; link.download = 'ax-rehearsal-' + String(state.result.run_id).replace(/[^a-zA-Z0-9_-]/g, '_') + '.json'; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('reload').addEventListener('click', loadContext);
  document.querySelectorAll('.rail nav a').forEach((link) => link.addEventListener('click', () => {
    document.querySelectorAll('.rail nav a').forEach((item) => item.removeAttribute('aria-current')); link.setAttribute('aria-current', 'location');
  }));
  document.querySelector('.rail nav a').setAttribute('aria-current', 'location');
  loadContext();
})();
