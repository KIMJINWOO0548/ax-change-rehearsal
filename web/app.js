/* Local-only review workbench. Verdicts and evidence come from real server runs. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const review = globalThis.RehearsalReview;
  const state = {context:null, result:null, busy:false, revision:0, request:0, selected:null,
    stale:false, error:false, selectedIds:new Set(), history:[], comparison:null};
  const labels = {PASS_WITHIN_SCOPE:'범위 내 통과', FAIL:'불일치', INCONCLUSIVE:'판정 보류',
    PASS:'통과', INCOMPLETE:'불완전', CHANGE:'변경 대상', PRESERVE:'유지 대상', INDETERMINATE:'판단 유보',
    IMPROVED:'해결됨', REGRESSED:'새 실패', PERSISTING:'실패 유지', UNVERIFIED:'미확인 포함', UNCHANGED:'통과 유지', CHECK_REGRESSION:'검사 회귀'};
  const decisions = {ELIGIBLE:'반품 가능', INELIGIBLE:'반품 불가', NEEDS_INPUT:'입력 필요',
    INVALID_INPUT:'잘못된 입력', UNSUPPORTED:'지원 범위 밖'};
  const label = value => labels[value] || String(value ?? '미확인');
  const decision = value => value ? (decisions[value.decision] || value.decision || '응답 미확인') : '응답 미확인';
  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function badge(value) {
    const kind = ['PASS','PASS_WITHIN_SCOPE','IMPROVED','UNCHANGED'].includes(value) ? 'pass' :
      ['FAIL','REGRESSED','PERSISTING','CHECK_REGRESSION'].includes(value) ? 'fail' : 'unknown';
    return el('span', label(value), 'badge ' + kind);
  }
  function configuration() {
    return {faq_version:document.querySelector('input[name="faq_version"]:checked').value,
      api_version:document.querySelector('input[name="api_version"]:checked').value,
      case_ids:review.orderedSelection(state.context.cases, state.selectedIds)};
  }
  function status(text, kind='') { $('run-status').textContent=text; $('run-status').className='notice '+kind; }
  function renderWorkspace() {
    const context=state.context, result=state.result;
    let title='연결 확인 필요', next='정책과 사례를 불러온 뒤 실행할 수 있습니다.', target='policy', action='정책 확인으로 이동';
    let tone='neutral';
    if(context) {
      const config=configuration(), version=v=>v==='corrected'?'변경 반영':'이전 정책';
      $('workspace-scope').textContent=state.selectedIds.size+' / '+context.cases.length+'개'+(state.selectedIds.size===context.cases.length?' · 전체':' · 부분');
      $('workspace-versions').textContent=version(config.faq_version)+' / '+version(config.api_version);
      $('workspace-storage').textContent=context.storage?.enabled?'로컬 저장 켜짐':'이 탭에서만 확인';
      title='실행 준비';next='선택한 사례와 FAQ·API 버전을 확인하고 리허설을 실행하세요.';target='configuration';action='실행 설정으로 이동';
      if(context.policy_review_valid===false){title='정책 근거 재검토 필요';next='정책 원문이 변경되어 실행이 차단됐습니다.';target='policy';tone='error';action='변경 근거 확인';}
      else if(state.busy){title='리허설 실행 중';next='모의 응답과 독립 관찰 상태를 확인하고 있습니다.';target='results';action='실행 상태 확인';}
      else if(state.error){title='실행 확인 필요';next='완료되지 않은 실행입니다. 오류 내용을 확인한 뒤 다시 실행하세요.';target='results';tone='error';action='오류 내용 확인';}
      else if(!state.selectedIds.size){title='실행할 사례를 선택하세요';next='검색 결과와 선택 범위는 별개입니다. 한 개 이상 선택해야 실행할 수 있습니다.';target='scenarios';tone='warning';action='사례 선택으로 이동';}
      else if(state.stale){title='설정 변경 · 재실행 필요';next='이전 결과는 현재 선택 범위와 버전의 검증 결과가 아닙니다.';tone='warning';}
      else if(result){
        target='results';action='차이·근거 검토로 이동';
        if(result.counts.FAIL){title='불일치 '+result.counts.FAIL+'건 · 수정 필요';next='FAQ·API 결과와 정책 근거를 확인한 뒤 같은 범위로 다시 실행하세요.';tone='error';}
        else if(result.counts.INCONCLUSIVE){title='보류 '+result.counts.INCONCLUSIVE+'건 · 검토 필요';next='불일치가 없어도 입력 결측·범위 밖 사례는 통과가 아닙니다.';tone='warning';}
        else if(!result.scope.complete){title='선택 범위만 검증됨';next='미실행 사례를 포함해 다시 실행해야 등록 범위 전체를 검토할 수 있습니다.';tone='warning';}
        else {title='등록 범위 내 통과';next='합성 모의 실행 결과입니다. 실제 업무 적용이나 배포 승인을 뜻하지 않습니다.';tone='success';}
      }
    } else {
      for(const id of ['workspace-scope','workspace-versions','workspace-storage'])$(id).textContent='확인되지 않음';
    }
    $('workspace-title').textContent=title;$('workspace-next').textContent=next;
    $('workspace-action').textContent=action+' →';$('workspace-action').href='#'+target;
    document.querySelector('.workspace-overview')?.setAttribute('data-tone',tone);
    $('review-priority').disabled=!result||state.stale||state.busy;
  }
  function availability() {
    const blocked=!state.context || state.context.policy_review_valid===false || state.busy;
    $('run').disabled=blocked || state.selectedIds.size===0;
    for (const id of ['faq-field','api-field','scenario-field']) $(id).disabled=blocked;
    $('run').textContent=state.busy?'실행 중…':state.result?'다시 리허설 실행':'리허설 실행';
    $('download').disabled=!state.result || state.stale || state.busy;
    $('select-failed').disabled=!state.result || state.stale || state.busy || !state.result.cases.some(c=>c.business_verdict==='FAIL');
    $('compare-run').disabled=state.busy || state.history.length<2;
    $('results').setAttribute('aria-busy',String(state.busy));
    renderWorkspace();
  }
  async function request(path, options={}) {
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),30000);
    try {
      const response=await fetch(path,{...options,signal:controller.signal,credentials:'same-origin',cache:'no-store'});
      let data;
      try { data=await response.json(); } catch { throw new Error('서버가 올바른 JSON 응답을 보내지 않았습니다.'); }
      if (!response.ok) throw new Error(data.error?.message || '서버 요청 실패 ('+response.status+')');
      return data;
    } catch(error) {
      if(error.name==='AbortError') throw new Error('요청 시간이 초과됐습니다. 서버 상태를 확인하고 다시 실행하세요.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function invalidate() {
    state.revision++;state.error=false;
    if(state.result) {state.stale=true;status('설정이 변경됐습니다. 아래는 이전 실행 결과입니다. 다시 실행해야 현재 범위를 검증할 수 있습니다.','warning');}
    availability();
  }
  function renderPolicy(key) {
    const source=state.context.policy[key], counterpart=state.context.policy[key==='before'?'after':'before'];
    const other=new Set(counterpart.lines.map(l=>l.text)), lines=$(key+'-lines');lines.replaceChildren();
    for(const line of source.lines) {
      const row=el('div',undefined,'line'+(line.text&&!other.has(line.text)?' changed':''));
      row.append(el('span',line.number,'line-number'),el('span',line.text||' ','line-text'));lines.append(row);
    }
    const rule=source.lines.find(l=>l.number===7);
    $(key+'-change').textContent=rule ? rule.text : '등록된 변경 조항을 찾지 못했습니다.';
    $(key+'-source').textContent=source.path+'\nSHA-256 '+source.sha256;
  }
  function renderSelection() {
    if(!state.context)return;
    const search=$('case-search').value.trim().toLowerCase();
    const cases=state.context.cases, shown=cases.filter(c=>(c.id+' '+c.label).toLowerCase().includes(search));
    $('scenario-list').replaceChildren();
    for(const c of shown) {
      const row=el('label',undefined,'scenario-option'), input=el('input');
      input.type='checkbox';input.value=c.id;input.name='case_id';input.checked=state.selectedIds.has(c.id);
      input.addEventListener('change',()=>{if(input.checked)state.selectedIds.add(c.id);else state.selectedIds.delete(c.id);updateSelectionSummary(shown.length);invalidate();});
      const text=el('span');text.append(el('strong',c.label),el('small',c.id+' · '+label(c.intended_behavior)));
      row.append(input,text);$('scenario-list').append(row);
    }
    updateSelectionSummary(shown.length);
  }
  function updateSelectionSummary(shownCount) {
    const cases=state.context.cases;
    $('selection-count').textContent='선택 '+state.selectedIds.size+' / '+cases.length+'개 · 표시 '+shownCount+'개';
    $('scenario-count').textContent='선택한 '+state.selectedIds.size+'개 시나리오 · 모의 실행';
    $('scenario-empty').hidden=shownCount!==0;
    const omitted=cases.filter(c=>!state.selectedIds.has(c.id));
    $('scope-warning').hidden=omitted.length===0;
    $('scope-warning').textContent=state.selectedIds.size===0?'한 개 이상의 사례를 선택해야 실행할 수 있습니다.':
      '부분 실행입니다. 제외된 '+omitted.length+'개 ('+omitted.map(c=>c.id).join(', ')+')는 검증하지 않습니다.';
  }
  function selectCases(predicate) {
    if(state.busy || !state.context)return;
    state.selectedIds=new Set(state.context.cases.filter(predicate).map(c=>c.id));
    renderSelection();invalidate();
  }
  const archive=globalThis.RehearsalArchive?.mount(document,request);
  async function loadContext() {
    $('reload').hidden=true;$('connection').hidden=false;$('connection').textContent='정책과 시나리오를 불러오는 중입니다.';
    try {
      const context=await request('/api/context');
      if(!context.csrf_token || !context.policy?.before?.lines || !context.policy?.after?.lines ||
         !context.defaults || !context.project || !Array.isArray(context.cases) || !context.cases.length ||
         new Set(context.cases.map(c=>c.id)).size!==context.cases.length) throw new Error('정책 응답의 필수 정보가 없습니다.');
      state.context=context;state.error=false;archive?.configure(context);
      for(const name of ['faq_version','api_version']) {
        const input=Array.from(document.querySelectorAll('input[name="'+name+'"]')).find(i=>i.value===context.defaults[name]);
        if(!input)throw new Error('지원되지 않는 기본 버전입니다.');input.checked=true;
      }
      state.selectedIds=new Set(context.cases.map(c=>c.id));renderSelection();
      renderPolicy('before');renderPolicy('after');
      $('effective-date').textContent='시행일 '+context.change.effective_date;
      $('policy-change').textContent='반품 허용 기간 '+context.change.old_window_days+'일 → '+context.change.new_window_days+'일';
      $('before-days').textContent=context.change.old_window_days+'일 기준';$('after-days').textContent=context.change.new_window_days+'일 기준';
      document.querySelectorAll('.stale-label').forEach(n=>n.textContent='이전 정책 · '+context.change.old_window_days+'일');
      document.querySelectorAll('.corrected-label').forEach(n=>n.textContent='변경 반영 · '+context.change.new_window_days+'일');
      $('preserved').textContent='유지되는 조건 · '+context.change.preserved.join(' · ');
      renderLimits(context.limits);$('connection').hidden=true;
      if(context.policy_review_valid===false)status('정책 문서가 바뀌었습니다. 근거와 독립 시나리오를 다시 검토해야 실행할 수 있습니다.','error');
    } catch(error) {
      state.context=null;archive?.configure(null);$('connection').textContent='연결하지 못했습니다. '+error.message;$('connection').className='notice error';$('reload').hidden=false;
    } finally {availability();}
  }
  function renderLimits(limits) { $('limits').replaceChildren(...(limits||[]).map(item=>el('li',item))); }
  function raw(title,value) { const d=el('details',undefined,'raw-object');d.append(el('summary',title),el('pre',JSON.stringify(value??null,null,2)));return d; }
  function showDetail(item,focus=true) {
    state.selected=item.id;
    $('detail-title').textContent=item.label+' · '+item.id;$('detail-reason').textContent=item.reason||'별도 판정 사유가 없습니다.';
    const facts=$('detail-facts');facts.replaceChildren();
    for(const [title,value] of [['업무 판정',label(item.business_verdict)],['진단 검사',label(item.assertion_status)],['의도한 동작',label(item.intended_behavior)]])
      facts.append(el('dt',title),el('dd',value));
    const summary=item.decision_summary||{}, expected=summary.expected;
    const comparison=$('decision-comparison');comparison.replaceChildren(el('h3','기대값과 실제 응답'));
    const grid=el('div',undefined,'decision-grid');
    for(const [name,value] of [['변경 후 기대값',expected],['FAQ 응답',summary.faq],['기준 API 응답',summary.baseline_api],['후보 API 응답',summary.candidate_api]]) {
      const cell=el('div',undefined,'decision-cell');cell.append(el('span',name),el('strong',decision(value)),el('small',value?.status||'UNKNOWN'));
      if(name!=='변경 후 기대값' && name!=='기준 API 응답' && expected &&
         (!value || value.decision!==expected.decision || value.status!==expected.status))cell.className+=' mismatch';
      grid.append(cell);
    }
    comparison.append(grid,el('p','기준 API는 변경 전 규정입니다. 후보와 다르다는 사실만으로 오류로 판정하지 않습니다.','section-note'));
    const observation=item.state_summary, container=$('state-comparison');container.replaceChildren(el('h3','독립적으로 관찰한 저장 상태'));
    if(observation) {
      const row=el('div',undefined,'state-metrics');
      for(const [title,value] of [['기대 생성',observation.expected_count],['첫 호출 후',observation.observed_count],['재호출 후',observation.replay_count]])
        {const cell=el('div');cell.append(el('span',title),el('strong',value===null?'미확인':String(value)+'건'));row.append(cell);}
      container.append(row);
      const checks=el('p',undefined,'state-checks');checks.append(badge(observation.verification),el('span',' 대상·작업 키·입력·저장 내용·재호출 불변성을 함께 검사합니다.'));
      container.append(checks);
      if(observation.errors?.length) {const errors=el('ul');for(const error of observation.errors)errors.append(el('li',error));container.append(errors);}
      if(item.business_verdict==='INCONCLUSIVE')container.append(el('p','진단 검사가 통과해도 입력 또는 업무 판단이 미확인이면 보류합니다.','notice warning'));
    } else container.append(el('p','상태 관찰 요약이 없습니다. 원시 근거를 확인하세요.','notice warning'));
    $('detail-evidence').replaceChildren(el('h3','정책 근거'));
    for(const evidence of item.evidence||[]) {
      const block=el('div',undefined,'evidence');
      block.append(el('p',evidence.quote),el('p',evidence.path+':'+evidence.line+'\nSHA-256 '+evidence.sha256,'mono'));
      $('detail-evidence').append(block);
    }
    $('detail-objects').replaceChildren(raw('업무 입력',item.input),raw('FAQ 실제 응답과 검증',item.faq),
      raw('후보 API 실제 응답 · 상태 관찰',item.candidate),raw('기준 API 실제 응답 · 상태 관찰',item.baseline));
    $('case-detail').hidden=false;renderRows();if(focus)$('case-detail').focus();
  }
  function renderRows() {
    if(!state.result)return;
    const filter=$('verdict-filter').value, changeFilter=$('change-filter').value;
    const changes=new Map((state.comparison?.rows||[]).map(c=>[c.id,c]));
    const rows=state.result.cases.filter(c=>(filter==='all'||c.business_verdict===filter) &&
      (!state.comparison?.comparable||changeFilter==='all'||(changeFilter==='REGRESSED'?changes.get(c.id)?.hasRegression:changes.get(c.id)?.change===changeFilter)));
    $('case-rows').replaceChildren();
    for(const item of rows) {
      const row=el('tr',undefined,state.selected===item.id?'selected':'');
      const name=el('td',item.label);name.append(el('span',item.id,'case-id'));
      const faq=el('td'), api=el('td'), verdict=el('td'), change=el('td'), action=el('td');
      faq.append(badge(item.faq?.assertion_status));api.append(badge(item.candidate?.assertion_status));verdict.append(badge(item.business_verdict));
      change.append(state.comparison?.comparable?badge(changes.get(item.id)?.hasRegression&&changes.get(item.id)?.change!=='REGRESSED'?'CHECK_REGRESSION':changes.get(item.id)?.change):el('span','비교 없음','muted'));
      const button=el('button','근거 보기','secondary');button.type='button';
      button.setAttribute('data-case-id',item.id);button.setAttribute('aria-label',item.label+' 근거 보기');
      button.setAttribute('aria-controls','case-detail');button.setAttribute('aria-expanded',String(state.selected===item.id));
      button.addEventListener('click',()=>showDetail(item));action.append(button);row.append(name,faq,api,verdict,change,action);$('case-rows').append(row);
    }
    $('visible-count').textContent=rows.length+' / '+state.result.cases.length+'개 표시';$('no-results').hidden=rows.length!==0;
  }
  function renderComparison() {
    const previous=state.history.find(r=>r.run_id===$('compare-run').value);
    state.comparison=previous?review.compareRuns(previous,state.result):null;
    $('change-filter').disabled=!state.comparison?.comparable;
    $('change-filter').value='all';
    $('comparison-summary').textContent=!previous?'같은 범위로 다시 실행하면 수정 효과를 비교할 수 있습니다.':
      !state.comparison.comparable?state.comparison.reason:
      '업무 해결 '+state.comparison.improved+' · 새 실패 '+state.comparison.regressed+' · 미확인 포함 '+state.comparison.unverified+
      ' | FAQ 검사 개선 '+state.comparison.faqImproved+' · API 검사 개선 '+state.comparison.apiImproved+
      ' | FAQ 회귀 '+state.comparison.faqRegressed+' · API 회귀 '+state.comparison.apiRegressed;
    renderRows();
  }
  function renderResult() {
    const result=state.result;$('result-content').hidden=false;$('case-detail').hidden=true;state.selected=null;
    $('summary').replaceChildren();
    for(const [name,count] of [['실행한 사례',result.total],['범위 내 통과',result.counts.PASS_WITHIN_SCOPE||0],['불일치',result.counts.FAIL||0],['판정 보류',result.counts.INCONCLUSIVE||0]]) {
      const item=el('div',undefined,'summary-item');item.setAttribute('data-kind',name==='불일치'?'fail':name==='판정 보류'?'unknown':name==='범위 내 통과'?'pass':'total');item.append(el('strong',count),el('span',name));$('summary').append(item);
    }
    const urgent=result.counts.FAIL?'FAIL':result.counts.INCONCLUSIVE?'INCONCLUSIVE':null;
    $('review-priority').hidden=!urgent;
    $('review-priority').textContent=urgent==='FAIL'?'불일치 근거부터 보기':'보류 근거부터 보기';
    $('review-next-text').textContent=urgent==='FAIL'?'먼저 불일치 사례의 기대값·실제 응답·저장 상태를 대조하세요.':urgent==='INCONCLUSIVE'?'보류 사례의 누락 입력과 지원 범위를 확인하세요. 진단 검사 통과와 업무 통과는 다릅니다.':'선택 범위의 근거를 검토하고, 필요한 경우 로컬 검토 메모를 남기세요.';
    $('result-scope').textContent=result.scope.complete?'등록된 '+result.scope.registered_total+'개 사례 전체를 실행했습니다.':
      '부분 실행 '+result.scope.selected_total+' / '+result.scope.registered_total+'개. 미실행: '+result.scope.omitted_case_ids.join(', ')+'. 전체 범위를 검증한 결과가 아닙니다.';
    $('result-scope').className=result.scope.complete?'section-note':'notice warning';
    $('run-meta').textContent='실행 '+result.run_id+' · '+result.created_at+'\nFAQ '+result.configuration.faq_version+' / API '+result.configuration.api_version+
      '\n선택 '+result.scope.selected_case_ids.join(', ')+'\nManifest SHA-256 '+result.manifest_sha256;
    $('verdict-filter').replaceChildren(new Option('전체','all'),...[...new Set(result.cases.map(c=>c.business_verdict))].map(v=>new Option(label(v),v)));
    const old=state.history.filter(r=>r.run_id!==result.run_id);
    $('compare-run').replaceChildren(new Option('비교 안 함',''),...old.map((r,i)=>new Option(
      (state.history.length-i-1)+'번째 · FAQ '+r.configuration.faq_version+' / API '+r.configuration.api_version+' · '+r.total+'개',r.run_id)));
    $('compare-run').value=old[0]?.run_id||'';renderComparison();renderLimits(result.limits);
    const readiness={BLOCKED:'불일치 수정 필요',REVIEW_REQUIRED:'보류 사례 검토 필요',PARTIAL_SCOPE:'선택 범위만 검증됨',PASS_WITHIN_REGISTERED_SCOPE:'등록 범위 내 통과'}[result.readiness]||'결과 검토 필요';
    status('실행 완료 · '+readiness+'. '+(!result.scope.complete?'일부 사례만 실행했습니다. ':'')+'아래 판정은 이 모의 실행의 범위에 한합니다.',
      result.readiness==='BLOCKED'?'error':result.readiness==='PASS_WITHIN_REGISTERED_SCOPE'?'success':'warning');
  }
  function validateResult(result,config) {
    const ids=result?.cases?.map(c=>c.id), selected=config.case_ids;
    if(!Array.isArray(ids)||!ids.length||ids.join('|')!==selected.join('|')||result.total!==selected.length||
       result.configuration?.faq_version!==config.faq_version||result.configuration?.api_version!==config.api_version||
       result.configuration?.case_ids?.join('|')!==selected.join('|')||!result.run_id||!result.manifest_sha256||
       result.scope?.selected_case_ids?.join('|')!==selected.join('|')||result.scope.selected_total!==selected.length||
       result.scope.registered_total!==state.context.cases.length||result.scope.complete!==(selected.length===state.context.cases.length))
      throw new Error('실행 결과의 사례·설정·범위가 요청과 일치하지 않습니다.');
    const omitted=state.context.cases.filter(c=>!selected.includes(c.id)).map(c=>c.id);
    if(!Array.isArray(result.scope.omitted_case_ids)||result.scope.omitted_case_ids.join('|')!==omitted.join('|'))
      throw new Error('미실행 사례 목록이 요청 범위와 일치하지 않습니다.');
    const actual={};
    for(const c of result.cases) {
      if(!['PASS_WITHIN_SCOPE','FAIL','INCONCLUSIVE'].includes(c.business_verdict))throw new Error('알 수 없는 업무 판정입니다.');
      actual[c.business_verdict]=(actual[c.business_verdict]||0)+1;
    }
    if(!result.counts||Object.keys(result.counts).some(k=>!(k in actual)&&result.counts[k]!==0)||
       Object.keys(actual).some(k=>result.counts[k]!==actual[k]))throw new Error('집계와 사례별 결과가 일치하지 않습니다.');
    const expectedReadiness=actual.FAIL?'BLOCKED':actual.INCONCLUSIVE?'REVIEW_REQUIRED':!result.scope.complete?'PARTIAL_SCOPE':'PASS_WITHIN_REGISTERED_SCOPE';
    if(result.readiness!==expectedReadiness)throw new Error('준비 상태와 사례별 판정·실행 범위가 일치하지 않습니다.');
  }
  async function run(event) {
    event.preventDefault();
    if(state.busy||!state.context||state.context.policy_review_valid===false)return;
    const config=configuration();if(!review.validSelection(state.context.cases,config.case_ids))return;
    state.busy=true;state.error=false;const token=++state.request,revision=state.revision;availability();
    status('선택한 시나리오의 응답과 저장 상태를 확인하고 있습니다.');if(state.result)state.stale=true;
    try {
      const result=await request('/api/run',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':state.context.csrf_token},body:JSON.stringify(config)});
      if(token!==state.request||revision!==state.revision) {status('설정이 변경되어 진행 중인 응답을 사용하지 않았습니다. 다시 실행하세요.','warning');return;}
      validateResult(result,config);state.result=result;state.stale=false;
      archive?.afterRun(result);
      state.history=[result,...state.history.filter(r=>r.run_id!==result.run_id)].slice(0,8);renderResult();
    } catch(error) {
      if(token===state.request){state.error=true;status('실행하지 못했습니다. '+error.message+(state.result?' 아래는 이전 실행 결과이며 현재 결과가 아닙니다.':'')+' 다시 실행하세요.','error');}
    } finally {if(token===state.request){state.busy=false;availability();}}
  }
  $('run-form').addEventListener('submit',run);$('run-form').addEventListener('change',invalidate);
  $('case-search').addEventListener('input',renderSelection);
  $('select-all').addEventListener('click',()=>selectCases(()=>true));
  $('select-none').addEventListener('click',()=>selectCases(()=>false));
  $('select-boundary').addEventListener('click',()=>selectCases(c=>c.tags.includes('boundary')));
  $('select-exception').addEventListener('click',()=>selectCases(c=>c.tags.includes('exception')));
  $('select-unknown').addEventListener('click',()=>selectCases(c=>c.intended_behavior==='INDETERMINATE'));
  $('select-failed').addEventListener('click',()=>{
    if($('select-failed').disabled)return;
    const ids=new Set(state.result.cases.filter(c=>c.business_verdict==='FAIL').map(c=>c.id));
    selectCases(c=>ids.has(c.id));$('scenarios-title').setAttribute('tabindex','-1');$('scenarios-title').focus();
  });
  for(const id of ['verdict-filter','change-filter']) $(id).addEventListener('change',()=>{state.selected=null;$('case-detail').hidden=true;renderRows();});
  $('compare-run').addEventListener('change',()=>{state.selected=null;$('case-detail').hidden=true;renderComparison();});
  $('review-priority').addEventListener('click',()=>{
    if($('review-priority').disabled)return;
    const verdict=state.result.counts.FAIL?'FAIL':'INCONCLUSIVE';
    $('verdict-filter').value=verdict;$('change-filter').value='all';
    const item=state.result.cases.find(c=>c.business_verdict===verdict);if(item)showDetail(item);
  });
  $('close-detail').addEventListener('click',()=>{
    const selected=state.selected;state.selected=null;$('case-detail').hidden=true;renderRows();
    const button=Array.from(document.querySelectorAll('#case-rows button')).find(b=>b.getAttribute('data-case-id')===selected);
    (button||$('verdict-filter')).focus();
  });
  $('download').addEventListener('click',()=>{
    if(!state.result||state.stale||state.busy)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(state.result,null,2)],{type:'application/json'}));
    const link=el('a');link.href=url;link.download='ax-rehearsal-'+String(state.result.run_id).replace(/[^a-zA-Z0-9_-]/g,'_')+'.json';
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  $('reload').addEventListener('click',loadContext);
  document.querySelectorAll('.rail nav a').forEach(link=>link.addEventListener('click',()=>{
    document.querySelectorAll('.rail nav a').forEach(item=>item.removeAttribute('aria-current'));link.setAttribute('aria-current','location');
  }));
  document.querySelector('.rail nav a').setAttribute('aria-current','location');loadContext();
})();
