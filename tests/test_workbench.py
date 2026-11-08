import copy
import unittest
from collections import Counter
from rehearsal.workbench import build_workbench, load_faq, faq_answer, ROOT
from rehearsal.report import render_html
from rehearsal.adapters import digest


class WorkbenchTests(unittest.TestCase):
    def test_three_stages_are_actual_runs(self):
        report = build_workbench()
        first, middle, last = report['stages']
        self.assertEqual([s['api']['variant'] for s in report['stages']], ['stale_candidate', 'stale_candidate', 'normal'])
        self.assertGreater(first['faq']['counts'].get('FAIL', 0), 0)
        self.assertEqual(middle['faq']['counts'].get('FAIL', 0), 0)
        self.assertGreater(middle['api']['counts'].get('FAIL', 0), 0)
        self.assertEqual(last['api']['counts'].get('FAIL', 0), 0)
        self.assertEqual(last['readiness'], 'REVIEW_REQUIRED')
        for stage in report['stages']:
            self.assertEqual(stage['counts'], dict(Counter(row['business_verdict'] for row in stage['cases'])))
        before = next(c for c in first['api']['cases'] if c['id'] == 'S04')
        after = next(c for c in last['api']['cases'] if c['id'] == 'S04')
        self.assertEqual(before['candidate']['observed_state'], [])
        self.assertEqual(len(after['candidate']['observed_state']), 1)

    def test_edit_invalidates_faq_review(self):
        faq = load_faq(ROOT / 'examples/customer_service/faq_corrected.json')
        edited = copy.deepcopy(faq)
        edited['content']['new_window_days'] = 14
        report = build_workbench(corrected_faq=edited)
        self.assertFalse(report['stages'][-1]['faq']['review_valid'])
        self.assertNotEqual(report['stages'][-1]['faq']['sha256'], build_workbench()['stages'][-1]['faq']['sha256'])
        self.assertTrue(all(c['business_verdict'] == 'INCONCLUSIVE' for c in report['stages'][-1]['faq']['cases']))

    def test_reviewed_wrong_configuration_is_not_used_as_oracle(self):
        faq = load_faq(ROOT / 'examples/customer_service/faq_corrected.json')
        faq['content']['new_window_days'] = 14
        faq['review']['content_sha256'] = digest(faq['content'])
        final = build_workbench(corrected_faq=faq)['stages'][-1]
        self.assertTrue(final['faq']['review_valid'])
        self.assertGreater(final['faq']['counts'].get('FAIL', 0), 0)
        self.assertEqual(final['api']['counts'].get('FAIL', 0), 0)
        self.assertEqual(final['readiness'], 'BLOCKED')

    def test_invalid_configuration_is_inconclusive(self):
        faq = load_faq(ROOT / 'examples/customer_service/faq_corrected.json')
        del faq['content']['effective_date']
        faq['review']['content_sha256'] = digest(faq['content'])
        self.assertFalse(build_workbench(corrected_faq=faq)['stages'][-1]['faq']['review_valid'])

    def test_runs_are_reproducible(self):
        self.assertEqual(build_workbench(), build_workbench())

    def test_faq_only_receives_business_input(self):
        faq = load_faq(ROOT / 'examples/customer_service/faq_corrected.json')
        data = {'order_id': 'test', 'region': 'KR', 'delivered_on': '2026-12-01', 'elapsed_days': 20, 'opened': False, 'custom_made': False}
        self.assertEqual(faq_answer(faq['content'], data)['decision'], 'ELIGIBLE')
        data['delivered_on'] = None
        self.assertEqual(faq_answer(faq['content'], data)['decision'], 'NEEDS_INPUT')

    def test_html_escapes_untrusted_text_and_has_no_remote_code(self):
        report = build_workbench()
        attack = '<script>alert("bad")</script><img src=x onerror=alert(1)>'
        report['stages'][0]['api']['cases'][0]['label'] = attack
        html = render_html(report)
        self.assertNotIn('<script', html.lower())
        self.assertNotIn('<img', html.lower())
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('https://', html)
        self.assertIn('Content-Security-Policy', html)


if __name__ == '__main__':
    unittest.main()
