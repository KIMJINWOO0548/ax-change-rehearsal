"""Incomplete evaluator output and changed JSON types are not completion proof."""
import copy
import json
import unittest
from unittest.mock import patch

from rehearsal import workbench
from rehearsal.adapters import digest
from rehearsal.app import execute_run
from rehearsal.replay import replay_report


class WorkbenchCompletionTests(unittest.TestCase):
    def test_incomplete_duplicate_or_reordered_results_never_form_a_report(self):
        def corrupt(result, mutation):
            if mutation == 'empty':
                result['cases'] = []
            elif mutation == 'missing':
                result['cases'].pop()
            elif mutation == 'duplicate':
                result['cases'][-1] = copy.deepcopy(result['cases'][0])
            elif mutation == 'reordered':
                result['cases'].reverse()
            elif mutation == 'unknown-id':
                result['cases'][0]['id'] = 'UNREGISTERED_SYNTHETIC_CASE'
            else:
                result['cases'] = None
            return result

        for evaluator in ('run_pack', 'evaluate_faq'):
            original = getattr(workbench, evaluator)
            for mutation in ('empty', 'missing', 'duplicate', 'reordered', 'unknown-id', 'malformed'):
                with self.subTest(evaluator=evaluator, mutation=mutation):
                    with patch.object(workbench, evaluator,
                                      side_effect=lambda *args, **kwargs: corrupt(original(*args, **kwargs), mutation)):
                        with self.assertRaisesRegex(ValueError, 'Execution results do not match the registered scope'):
                            workbench.build_workbench()

    def test_unknown_business_verdict_is_not_coerced_to_pass(self):
        for evaluator in ('run_pack', 'evaluate_faq'):
            original = getattr(workbench, evaluator)
            for verdict in ('EXECUTION_ERROR', None, [], {}):
                def unknown(*args, **kwargs):
                    result = original(*args, **kwargs)
                    result['cases'][0]['business_verdict'] = verdict
                    return result
                with self.subTest(evaluator=evaluator, verdict=verdict), patch.object(workbench, evaluator, side_effect=unknown):
                    with self.assertRaisesRegex(ValueError, 'Execution results do not match the registered scope'):
                        workbench.build_workbench()

    def test_normal_stages_keep_registered_cases_and_unknowns(self):
        result = workbench.build_workbench()
        self.assertEqual(result, workbench.build_workbench())
        for stage, failures in zip(result['stages'], (4, 4, 0)):
            self.assertEqual(len(stage['cases']), 12)
            self.assertEqual([row['id'] for row in stage['cases']],
                             [row['id'] for row in stage['api']['cases']])
            self.assertEqual(stage['counts'].get('FAIL', 0), failures)
            self.assertEqual(stage['counts']['INCONCLUSIVE'], 3)
            self.assertEqual(sum(stage['counts'].values()), 12)
            self.assertEqual(stage['readiness'], 'BLOCKED' if failures else 'REVIEW_REQUIRED')


class ReplayJsonIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.report = execute_run({'faq_version': 'corrected', 'api_version': 'corrected',
                                   'case_ids': ['S01']})

    def test_equal_numeric_values_of_different_json_types_are_not_a_match(self):
        for field in ('counts-float', 'counts-bool', 'total-float', 'state-count-float'):
            with self.subTest(field=field):
                report = copy.deepcopy(self.report)
                if field == 'counts-float':
                    report['counts']['PASS_WITHIN_SCOPE'] = 1.0
                elif field == 'counts-bool':
                    report['counts']['PASS_WITHIN_SCOPE'] = True
                elif field == 'total-float':
                    report['total'] = 1.0
                else:
                    state = report['cases'][0]['state_summary']
                    state['expected_count'] = float(state['expected_count'])
                before = copy.deepcopy(report)
                result = replay_report(report)
                self.assertEqual(result['status'], 'DIFFERENT')
                self.assertTrue(result['changed_sections'])
                self.assertFalse(result['deployment_approval'])
                self.assertEqual(report, before)

    def test_scope_boolean_changed_to_integer_is_rejected_before_replay(self):
        report = copy.deepcopy(self.report)
        report['scope']['complete'] = 0
        with patch('rehearsal.replay.execute_run', wraps=execute_run) as run:
            with self.assertRaisesRegex(ValueError, 'Replay evidence is missing or inconsistent'):
                replay_report(report)
            run.assert_not_called()

    def test_changed_manifest_json_type_is_incompatible(self):
        report = copy.deepcopy(self.report)
        report['scope']['complete'] = 0
        report['manifest']['scope']['complete'] = 0
        report['manifest_sha256'] = digest(report['manifest'])
        result = replay_report(report)
        self.assertEqual(result['status'], 'INCOMPATIBLE')
        self.assertFalse(result['deployment_approval'])

    def test_explicit_null_section_does_not_match_an_absent_section(self):
        report = copy.deepcopy(self.report)
        report['unexpected_section'] = None
        result = replay_report(report)
        self.assertEqual(result['status'], 'DIFFERENT')
        self.assertEqual(result['changed_sections'], ['unexpected_section'])

    def test_json_roundtrip_keeps_partial_and_inconclusive_match_meaning(self):
        report = json.loads(json.dumps(self.report, sort_keys=True))
        result = replay_report(report)
        self.assertEqual(result['status'], 'MATCH')
        self.assertEqual(result['readiness'], 'PARTIAL_SCOPE')
        self.assertIs(result['scope']['complete'], False)
        full = execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})
        result = replay_report(json.loads(json.dumps(full, sort_keys=True)))
        self.assertEqual(result['status'], 'MATCH')
        self.assertEqual(result['counts']['INCONCLUSIVE'], 3)
        self.assertEqual(result['readiness'], 'REVIEW_REQUIRED')
        self.assertFalse(result['deployment_approval'])


if __name__ == '__main__':
    unittest.main()
