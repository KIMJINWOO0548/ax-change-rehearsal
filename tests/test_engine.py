"""Independent regression checks for runner safety and injected defects."""
import copy
import unittest
from unittest.mock import patch

from rehearsal.adapters import ADAPTERS, CustomerServiceAdapter, OperationConflict, VARIANTS
from rehearsal.engine import load_packs, run_pack, run_side, run_suite


class EngineSafetyTests(unittest.TestCase):
    def setUp(self):
        self.pack = load_packs(['customer_service'])[0]
        self.case = self.pack['cases'][1]

    def run_side(self, adapter):
        return run_side(adapter, 'candidate_v2', 'normal', self.case,
                        self.case['expected_after'], 'safety-check')

    def test_empty_pack_is_rejected_instead_of_green(self):
        self.pack['cases'] = []
        with self.assertRaises(ValueError):
            run_pack(self.pack)

    def test_duplicate_case_ids_are_rejected(self):
        self.pack['cases'][1]['id'] = self.pack['cases'][0]['id']
        with self.assertRaises(ValueError):
            run_pack(self.pack)

    def test_invalid_metadata_date_is_rejected(self):
        self.pack['effective_date'] = '2026-02-30'
        with self.assertRaises(ValueError):
            run_pack(self.pack)

    def test_changed_policy_date_cannot_silently_reuse_hardcoded_adapter(self):
        self.pack['effective_date'] = '2027-01-01'
        with self.assertRaises(ValueError):
            run_pack(self.pack)

    def test_source_path_cannot_leave_domain(self):
        self.pack['source_documents']['after'] = '../../README.md'
        with self.assertRaises(ValueError):
            run_pack(self.pack)

    def test_invalid_expected_count_is_rejected(self):
        self.pack['cases'][0]['expected_before']['state_delta']['count'] = True
        with self.assertRaises(ValueError):
            run_pack(self.pack)

    def test_conflicting_intent_is_rejected(self):
        self.pack['cases'][0]['intended_behavior'] = 'CHANGE'
        with self.assertRaises(ValueError):
            run_pack(self.pack)

    def test_empty_or_duplicate_requested_domains_are_rejected(self):
        for domains in ([], ['finance', 'finance']):
            with self.subTest(domains=domains), self.assertRaises(ValueError):
                load_packs(domains)

    def test_empty_or_duplicate_variants_are_rejected(self):
        for variants in ([], ['normal', 'normal']):
            with self.subTest(variants=variants), self.assertRaises(ValueError):
                run_suite(variants)

    def test_observe_after_write_then_timeout_without_replaying(self):
        class TimeoutAfterWrite(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                super().invoke(env, key, data)
                raise TimeoutError('response lost after write')
        result = self.run_side(TimeoutAfterWrite())
        self.assertEqual(len(result['observed_state'] or []), 1)
        self.assertEqual(result['invocation_error']['type'], 'TimeoutError')
        self.assertIsNone(result['observation_error'])
        self.assertIsNone(result['replay_response'])
        self.assertEqual(result['assertion_status'], 'INCOMPLETE')

    def test_wrong_effect_is_failed_even_when_response_times_out(self):
        class WrongWriteThenTimeout(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                super().invoke(env, key, data)
                env.rows[-1]['target_id'] = 'wrong-order'
                raise TimeoutError('lost response')
        result = self.run_side(WrongWriteThenTimeout())
        self.assertEqual(result['assertion_status'], 'FAIL')
        self.assertTrue(any('state_target_id' in e for e in result['assertion_errors']))

    def test_initial_observation_error_prevents_invocation(self):
        class MustNotInvoke(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                raise AssertionError('unsafe invocation after unreadable initial state')
        with patch('rehearsal.engine.observe', side_effect=TimeoutError('initial read failed')):
            result = self.run_side(MustNotInvoke())
        self.assertEqual(result['assertion_status'], 'INCOMPLETE')
        self.assertIsNone(result['response'])
        self.assertIsNone(result['invocation_error'])
        self.assertEqual(result['observation_error']['stage'], 'initial')

    def test_none_response_is_not_pass(self):
        class MissingResponse(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                return None
        self.assertEqual(self.run_side(MissingResponse())['assertion_status'], 'FAIL')

    def test_replay_cannot_repair_false_success_and_hide_first_failure(self):
        class ReplayRepairsWrite(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                response = super().invoke(env, key, data)
                if env.invocation_count == 1:
                    env.rows.clear()
                else:
                    self._write(env, key, data, response['decision'])
                return response
        result = self.run_side(ReplayRepairsWrite())
        self.assertEqual(result['assertion_status'], 'FAIL')
        self.assertTrue(any('state_count' in e for e in result['assertion_errors']))

    def test_malformed_initial_observation_is_unknown_not_pass(self):
        for malformed in (None, {}, [None], 'not-a-snapshot'):
            with self.subTest(malformed=malformed):
                with patch('rehearsal.engine.observe', return_value=malformed):
                    result = self.run_side(CustomerServiceAdapter())
                self.assertEqual(result['assertion_status'], 'INCOMPLETE')
                self.assertEqual(result['effect_status'], 'UNKNOWN_EFFECT')
                self.assertIsNone(result['response'])

    def test_malformed_after_observation_is_unknown_not_pass(self):
        with patch('rehearsal.engine.observe', side_effect=[[], None]):
            result = self.run_side(CustomerServiceAdapter())
        self.assertEqual(result['assertion_status'], 'INCOMPLETE')
        self.assertEqual(result['effect_status'], 'UNKNOWN_EFFECT')
        self.assertIsNone(result['replay_response'])

    def test_key_conflict_preserves_effect_and_receipt(self):
        adapter = CustomerServiceAdapter()
        env = adapter.create_environment('candidate_v2')
        data = self.case['business_input']
        first = adapter.invoke(env, 'repeat', data)
        changed = {**data, 'order_id': 'another-order'}
        with self.assertRaises(OperationConflict):
            adapter.invoke(env, 'repeat', changed)
        self.assertEqual(adapter.invoke(env, 'repeat', data), first)
        self.assertEqual(len(env.rows), 1)
        self.assertEqual(env.rows[0]['target_id'], data['order_id'])

    def test_manifest_and_results_are_deterministic(self):
        self.assertEqual(run_pack(self.pack), run_pack(copy.deepcopy(self.pack)))

    def test_oracles_never_reach_adapter(self):
        class InputGuard(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                if any(k not in self.fields for k in data):
                    raise AssertionError('oracle or other metadata leaked')
                return super().invoke(env, key, data)
        with patch.dict(ADAPTERS, {'customer_service': InputGuard}):
            result = run_pack(self.pack)
        self.assertTrue(all(c['assertion_status'] == 'PASS' for c in result['cases']))


class MutationRegressionTests(unittest.TestCase):
    def test_every_injected_mutation_has_expected_detection(self):
        expected_failures = {'stale_candidate': 10, 'boundary': 5, 'exception_removed': 5,
            'wrong_effective_scope': 3, 'false_success': 11, 'duplicate_effect': 11,
            'wrong_target': 11, 'unknown_as_zero': 2, 'unexpected_write': 25}
        suite = run_suite(list(VARIANTS))
        summaries = {s['variant']: s for s in suite['summaries']}
        self.assertEqual(summaries['normal']['assertion_counts'], {'PASS': 36})
        self.assertEqual(summaries['normal']['business_counts'], {'PASS_WITHIN_SCOPE': 27, 'INCONCLUSIVE': 9})
        self.assertEqual(summaries['observer_timeout']['assertion_counts'], {'INCOMPLETE': 36})
        for name, fail in expected_failures.items():
            with self.subTest(variant=name):
                self.assertEqual(summaries[name]['assertion_counts'].get('FAIL'), fail)
                self.assertEqual(summaries[name]['cases'], 36)
