/* Pure, conservative comparison helpers shared by browser and dependency-free tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.RehearsalReview = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const stable = value => {
    if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + stable(value[k])).join(',') + '}';
    return JSON.stringify(value);
  };
  const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const hash = v => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
  const apiSources = ['rehearsal/engine.py','rehearsal/adapters.py','rehearsal/validation.py',
    'fixtures/customer_service/policy_before.md','fixtures/customer_service/policy_after.md'];
  function requiredHashes(value, keys) {
    if(!object(value))return false;
    const normalized=Object.fromEntries(Object.entries(value).map(([k,h])=>[k.replaceAll(String.fromCharCode(92),'/'),h]));
    return Object.keys(normalized).length===Object.keys(value).length && keys.every(k=>hash(normalized[k]));
  }
  const expectation = v => object(v) && typeof v.status==='string' && v.status.length>0 &&
    typeof v.decision==='string' && v.decision.length>0 && object(v.state_delta) &&
    typeof v.state_delta.table==='string' && v.state_delta.table.length>0 &&
    Number.isInteger(v.state_delta.count) && v.state_delta.count>=0;
  const provenance = m => object(m) && requiredHashes(m.policy_sha256,['before','after']) &&
    hash(m.registered_pack_sha256) && hash(m.api_manifest?.pack_digest) &&
    requiredHashes(m.api_manifest.sources,apiSources) &&
    requiredHashes(m.service_sources,['rehearsal/app.py','rehearsal/workbench.py']);
  const same = (a, b) => stable(a) === stable(b);
  function orderedSelection(cases, selected) { return cases.filter(c => selected.has(c.id)).map(c => c.id); }
  function validSelection(cases, ids) {
    return Array.isArray(ids) && ids.length > 0 && new Set(ids).size === ids.length &&
      ids.every(id => typeof id === 'string' && cases.some(c => c.id === id));
  }
  function compareRuns(previous, current) {
    const unavailable = reason => ({comparable: false, reason, rows: []});
    if (!previous || !current) return unavailable('비교할 이전 실행이 없습니다.');
    const a = previous.manifest, b = current.manifest;
    if (!provenance(a) || !provenance(b)) return unavailable('비교에 필요한 실행 근거가 없습니다.');
    if (!same(previous.scope?.selected_case_ids, current.scope?.selected_case_ids) ||
        !previous.scope?.selected_case_ids?.length) return unavailable('선택한 시나리오가 다릅니다. 같은 범위로 실행한 결과끼리 비교하세요.');
    if (a.registered_pack_sha256 !== b.registered_pack_sha256 || !same(a.policy_sha256, b.policy_sha256) || a.api_manifest.pack_digest !== b.api_manifest.pack_digest ||
        !same(a.api_manifest.sources, b.api_manifest.sources) || !same(a.service_sources, b.service_sources))
      return unavailable('정책·시나리오·실행 구현의 버전이 달라 직접 비교하지 않습니다.');
    if (!Array.isArray(previous.cases) || !Array.isArray(current.cases) ||
        previous.cases.length !== current.cases.length ||
        new Set(previous.cases.map(c => c.id)).size !== previous.cases.length ||
        new Set(current.cases.map(c => c.id)).size !== current.cases.length)
      return unavailable('사례 식별자 또는 실행 범위가 일치하지 않습니다.');
    for(const report of [previous,current]) {
      if(!same(report.cases.map(c=>c.id),report.scope.selected_case_ids) ||
         report.cases.some(c=>!object(c.input)||!expectation(c.candidate?.expected)||!expectation(c.baseline?.expected)||
           !['PASS','FAIL','INCOMPLETE'].includes(c.candidate.assertion_status)||
           !['PASS','FAIL','INCOMPLETE'].includes(c.faq?.assertion_status)))
        return unavailable('사례 입력·기대값·검사 근거 또는 선택 범위가 불완전합니다.');
    }
    const rows = [];
    for (const now of current.cases) {
      const old = previous.cases.find(c => c.id === now.id);
      if (!old || !same(old.input, now.input) || !same(old.candidate?.expected, now.candidate?.expected) || !same(old.baseline?.expected, now.baseline?.expected))
        return unavailable('사례 입력 또는 기대값이 달라 직접 비교하지 않습니다.');
      const before = old.business_verdict, after = now.business_verdict;
      const known = ['FAIL', 'PASS_WITHIN_SCOPE'];
      const change = !known.includes(before) || !known.includes(after) ? 'UNVERIFIED' :
        before === 'FAIL' && after === 'PASS_WITHIN_SCOPE' ? 'IMPROVED' :
        before === 'PASS_WITHIN_SCOPE' && after === 'FAIL' ? 'REGRESSED' :
        before === 'FAIL' && after === 'FAIL' ? 'PERSISTING' : 'UNCHANGED';
      const faqRegressed=old.faq?.assertion_status==='PASS'&&now.faq?.assertion_status==='FAIL';
      const apiRegressed=old.candidate?.assertion_status==='PASS'&&now.candidate?.assertion_status==='FAIL';
      rows.push({faqRegressed,apiRegressed,hasRegression:change==='REGRESSED'||faqRegressed||apiRegressed,id: now.id, change, before, after,
        faqImproved: old.faq?.assertion_status === 'FAIL' && now.faq?.assertion_status === 'PASS',
        apiImproved: old.candidate?.assertion_status === 'FAIL' && now.candidate?.assertion_status === 'PASS'});
    }
    return {comparable: true, rows, improved: rows.filter(r => r.change === 'IMPROVED').length,
      regressed: rows.filter(r => r.change === 'REGRESSED').length,
      unverified: rows.filter(r => r.change === 'UNVERIFIED').length,
      faqImproved: rows.filter(r => r.faqImproved).length, apiImproved: rows.filter(r => r.apiImproved).length,
      faqRegressed: rows.filter(r=>r.faqRegressed).length, apiRegressed: rows.filter(r=>r.apiRegressed).length};
  }
  return {compareRuns, orderedSelection, validSelection};
});
