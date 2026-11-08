const test = require('node:test');
const assert = require('node:assert/strict');
const review = require('../../web/review.js');
const {manifest,expected}=require('./comparison-fixtures.cjs');
const make = (values = ['FAIL', 'INCONCLUSIVE']) => ({
  scope: {selected_case_ids: ['S01', 'S02'], complete: true, registered_total: 2},
  manifest: manifest(),
  cases: values.map((verdict, i) => ({id: 'S0' + (i + 1), business_verdict: verdict,
    input: {value: i}, baseline:{expected:expected()}, candidate: {expected: expected(), assertion_status: verdict === 'FAIL' ? 'FAIL' : 'PASS'},
    faq: {assertion_status: verdict === 'FAIL' ? 'FAIL' : 'PASS'}}))
});
test('comparison keeps failures, improvements, regressions and unknowns separate', () => {
  const before = make(); const after = make(['PASS_WITHIN_SCOPE', 'INCONCLUSIVE']);
  const compared = review.compareRuns(before, after);
  assert.equal(compared.comparable, true);
  assert.equal(compared.rows[0].change, 'IMPROVED');
  assert.equal(compared.rows[1].change, 'UNVERIFIED');
  assert.equal(compared.faqImproved, 1);
  assert.equal(review.compareRuns(after, before).rows[0].change, 'REGRESSED');
});
test('FAQ-only fix is visible even while API still fails', () => {
  const before = make(); const after = make(); after.cases[0].faq.assertion_status = 'PASS';
  const compared = review.compareRuns(before, after);
  assert.equal(compared.rows[0].change, 'PERSISTING');
  assert.equal(compared.faqImproved, 1);
  assert.equal(compared.apiImproved, 0);
});
test('different scope or evidence revision cannot silently compare', () => {
  const before = make();
  for (const alter of [
    r => r.scope.selected_case_ids = ['S01'],
    r => r.manifest.policy_sha256.after = 'changed',
    r => r.manifest.api_manifest.pack_digest = 'changed',
    r => r.manifest.registered_pack_sha256 = 'changed',
    r => r.manifest.service_sources.app = 'changed',
    r => r.cases[0].input.value = 99,
    r => r.cases[0].candidate.expected.decision = 'INELIGIBLE',
    r => delete r.manifest
  ]) { const after = make(); alter(after); assert.equal(review.compareRuns(before, after).comparable, false); }
});
test('unknown outcomes never count as improvement and duplicate cases are rejected', () => {
  assert.equal(review.compareRuns(make(), make(['INCONCLUSIVE', 'INCONCLUSIVE'])).improved, 0);
  const after = make(); after.cases[1].id = 'S01';
  assert.equal(review.compareRuns(make(), after).comparable, false);
});
test('selection validates exact nonempty registered IDs and preserves registry order', () => {
  const cases = [{id:'S01'}, {id:'S02'}];
  assert.deepEqual(review.orderedSelection(cases, new Set(['S02','S01'])), ['S01','S02']);
  assert.equal(review.validSelection(cases, []), false);
  assert.equal(review.validSelection(cases, ['S01','S01']), false);
  assert.equal(review.validSelection(cases, ['unknown']), false);
  assert.equal(review.validSelection(cases, ['S02']), true);
});

test('crossed fixes expose FAQ regressions even when aggregate failure is unchanged', () => {
  const before=make(), after=make();
  before.cases[0].faq.assertion_status='PASS';
  after.cases[0].candidate.assertion_status='PASS';
  const compared=review.compareRuns(before,after);
  assert.equal(compared.faqRegressed,1);
  assert.equal(compared.apiImproved,1);
  assert.equal(compared.rows[0].hasRegression,true);
});
test('missing comparison evidence fails closed even when absent on both sides', () => {
  for(const alter of [
    r=>delete r.manifest.api_manifest.sources,
    r=>r.manifest.service_sources={},
    r=>r.manifest.policy_sha256={},
    r=>delete r.cases[0].input,
    r=>delete r.cases[0].candidate.expected
  ]) {const a=make(),b=make();alter(a);alter(b);assert.equal(review.compareRuns(a,b).comparable,false);}
});

test('each required provenance entry and complete baseline/candidate expectation is mandatory', () => {
  for(const alter of [
    r=>delete r.manifest.policy_sha256.after,
    r=>delete r.manifest.api_manifest.sources['rehearsal/engine.py'],
    r=>delete r.manifest.service_sources['rehearsal/app.py'],
    r=>r.manifest.api_manifest.pack_digest='invalid',
    r=>delete r.cases[0].candidate.expected.state_delta,
    r=>delete r.cases[0].baseline.expected,
    r=>r.cases[0].candidate.expected.state_delta.count=-1
  ]) {const a=make(),b=make();alter(a);alter(b);assert.equal(review.compareRuns(a,b).comparable,false);}
});
