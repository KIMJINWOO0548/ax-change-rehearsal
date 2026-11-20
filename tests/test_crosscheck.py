import copy
import unittest
from unittest.mock import patch

from rehearsal import app
from rehearsal.storage import validate_report


class CrosscheckTests(unittest.TestCase):
    def test_agreement_does_not_override_failed_independent_oracle(self):
        report = app.execute_run({'faq_version': 'stale', 'api_version': 'stale'})
        case = next(case for case in report['cases'] if case['business_verdict'] == 'FAIL')
        self.assertEqual(case['crosscheck']['state'], 'ALIGNED')
        self.assertEqual(case['crosscheck']['faq']['context_sha256'],
                         case['crosscheck']['api']['context_sha256'])
        self.assertEqual(case['business_verdict'], 'FAIL')
        self.assertEqual(report['manifest']['crosscheck_version'], 1)
        validate_report(report)

    def test_actual_path_input_change_is_not_called_decision_disagreement(self):
        evaluate = app.evaluate_faq

        def use_different_elapsed_days(config, pack):
            adjusted = copy.deepcopy(pack)
            for case in adjusted['cases']:
                case['business_input']['elapsed_days'] += 1
            return evaluate(config, adjusted)

        with patch.object(app, 'evaluate_faq', side_effect=use_different_elapsed_days):
            report = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected',
                                      'case_ids': ['S04']})
        self.assertEqual(report['cases'][0]['crosscheck']['state'], 'CONTEXT_MISMATCH')
        self.assertEqual(report['cases'][0]['crosscheck']['changed_fields'], ['elapsed_days'])

    def test_missing_response_and_bad_crosscheck_do_not_create_success(self):
        evaluate = app.evaluate_faq

        def without_response(config, pack):
            result = evaluate(config, pack)
            result['cases'][0]['response'] = None
            return result

        with patch.object(app, 'evaluate_faq', side_effect=without_response):
            report = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected',
                                      'case_ids': ['S04']})
        self.assertEqual(report['cases'][0]['crosscheck']['state'], 'UNOBSERVED')
        bad = copy.deepcopy(report)
        bad['cases'][0]['crosscheck']['state'] = 'ALIGNED'
        with self.assertRaises(ValueError):
            validate_report(bad)

        legacy = copy.deepcopy(report)
        del legacy['manifest']['crosscheck_version']
        del legacy['cases'][0]['crosscheck']
        validate_report(legacy)

    def test_stored_crosscheck_must_match_the_recorded_path_evidence(self):
        report = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected',
                                  'case_ids': ['S04']})
        check = report['cases'][0]['crosscheck']
        self.assertEqual(check['state'], 'ALIGNED')
        check['state'] = 'DIVERGENT'
        check['faq']['decision'] = ('ELIGIBLE' if check['api']['decision'] == 'INELIGIBLE' else 'INELIGIBLE')
        with self.assertRaises(ValueError):
            validate_report(report)
