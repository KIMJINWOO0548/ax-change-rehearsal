"""Product flow assertions remain separate from adapter/oracle implementation."""
import copy
import importlib.util
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from rehearsal.adapters import ADAPTERS, CustomerServiceAdapter, digest, observe


class InteractiveAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec('rehearsal.app') is not None:
            from rehearsal import app
            cls.app = app
        else:
            cls.app = None

    def require_app(self):
        self.assertIsNotNone(self.app, 'Interactive app service is not implemented')
        return self.app

    def test_context_includes_numbered_original_policy_evidence(self):
        context = self.require_app().build_context()
        self.assertEqual(context['project']['scenario_count'], 12)
        self.assertEqual(context['change']['new_window_days'], 30)
        self.assertEqual(context['defaults'], {'faq_version': 'stale', 'api_version': 'stale'})
        for side in ('before', 'after'):
            source = context['policy'][side]
            self.assertEqual('\n'.join(line['text'] for line in source['lines'])+'\n', source['text'])
            self.assertEqual([line['number'] for line in source['lines']], list(range(1,len(source['lines'])+1)))

    def test_all_four_artifact_combinations_run_real_regression(self):
        app = self.require_app()
        for faq, api, failed in [('stale','stale',4),('corrected','stale',4),
                                 ('stale','corrected',4),('corrected','corrected',0)]:
            with self.subTest(faq=faq,api=api):
                result = app.execute_run({'faq_version':faq,'api_version':api})
                self.assertEqual(result['total'],12)
                self.assertEqual(result['counts'].get('FAIL',0),failed)
                self.assertEqual(result['counts'].get('INCONCLUSIVE',0),3)
                self.assertEqual(result['readiness'],'BLOCKED' if failed else 'REVIEW_REQUIRED')
                self.assertEqual(result['configuration'],{'faq_version':faq,'api_version':api})
                self.assertEqual(len(result['manifest_sha256']),64)

    def test_evidence_lines_and_hashes_resolve_to_source(self):
        report = self.require_app().execute_run({'faq_version':'corrected','api_version':'corrected'})
        for case in report['cases']:
            self.assertTrue(case['reason'])
            self.assertTrue(case['evidence'])
            for ref in case['evidence']:
                source = report['policy']['after']
                self.assertEqual(ref['path'],source['path'])
                self.assertEqual(ref['sha256'],source['sha256'])
                self.assertEqual(ref['quote'],source['lines'][ref['line']-1]['text'])

    def test_api_correction_changes_observed_return_request(self):
        app = self.require_app()
        before = app.execute_run({'faq_version':'corrected','api_version':'stale'})
        after = app.execute_run({'faq_version':'corrected','api_version':'corrected'})
        b = next(c for c in before['cases'] if c['id']=='S04')
        a = next(c for c in after['cases'] if c['id']=='S04')
        self.assertEqual(b['candidate']['observed_state'],[])
        self.assertEqual(len(a['candidate']['observed_state']),1)
        self.assertEqual(a['candidate']['observed_state'][0]['target_id'],a['input']['order_id'])
        self.assertNotEqual(before['manifest_sha256'],after['manifest_sha256'])

    def test_run_identity_is_unique_while_manifest_reproducible(self):
        app = self.require_app()
        a=app.execute_run({'faq_version':'corrected','api_version':'corrected'})
        b=app.execute_run({'faq_version':'corrected','api_version':'corrected'})
        self.assertNotEqual(a['run_id'],b['run_id'])
        self.assertEqual(a['manifest_sha256'],b['manifest_sha256'])

    def test_changed_policy_requires_review_and_cannot_run(self):
        app=self.require_app()
        policy=app.build_context()['policy']
        policy['after']['sha256']='0'*64
        with patch('rehearsal.app._policy',return_value=policy):
            self.assertFalse(app.build_context()['policy_review_valid'])
            with self.assertRaises(ValueError):
                app.execute_run({'faq_version':'corrected','api_version':'corrected'})

    def test_faq_review_change_alters_manifest_and_explains_hold(self):
        app=self.require_app()
        config={'faq_version':'corrected','api_version':'corrected'}
        good=app.execute_run(config)
        faq=app.load_json(app.ROOT / 'examples/customer_service/faq_corrected.json')
        faq['review']['content_sha256']='0'*64
        with patch('rehearsal.app.load_json',return_value=faq):
            invalid=app.execute_run(config)
        self.assertNotEqual(good['manifest_sha256'],invalid['manifest_sha256'])
        self.assertEqual(invalid['counts'],{'INCONCLUSIVE':12})
        self.assertTrue(all('FAQ' in case['reason'] and '검토' in case['reason'] for case in invalid['cases']))

    def test_windows_newlines_preserve_reviewed_policy_identity(self):
        app=self.require_app()
        original=app.build_context()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for source in original['policy'].values():
                path=root / source['path']
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(source['text'].replace('\n','\r\n').encode('utf-8'))
            with patch('rehearsal.app.ROOT',root):
                actual=app.build_context()
        self.assertTrue(actual['policy_review_valid'])
        self.assertEqual(actual['policy'],original['policy'])

    def test_configuration_is_strict(self):
        app=self.require_app()
        for value in (None,[],{}, {'faq_version':'corrected'},
                      {'faq_version':'corrected','api_version':'hidden'},
                      {'faq_version':'corrected','api_version':'corrected','extra':1},
                      {'faq_version':['stale'],'api_version':'corrected'}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                app.execute_run(value)

    def test_optional_selection_is_strict_before_any_invocation(self):
        app = self.require_app()
        invalid = (None, [], 'S04', {'S04': True}, ('S04',), [None], [True], [4],
                   [['S04']], [{}], [''], ['s04'], [' S04'], ['S04 '], ['S99'],
                   ['S04', 'S04'], ['S04'] * 13)
        for selection in invalid:
            with self.subTest(selection=selection), patch('rehearsal.app.run_pack') as run:
                with self.assertRaises(ValueError):
                    app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected',
                                     'case_ids': selection})
                run.assert_not_called()

    def test_selected_cases_execute_only_selected_api_and_faq_inputs(self):
        app = self.require_app()
        from rehearsal.workbench import faq_answer
        seen = []

        class RecordingAdapter(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                seen.append((key.split(':')[1], copy.deepcopy(data)))
                return super().invoke(env, key, data)

        configuration = {'faq_version': 'corrected', 'api_version': 'corrected',
                         'case_ids': ['S04', 'S01']}
        with patch.dict(ADAPTERS, {'customer_service': RecordingAdapter}), \
                patch('rehearsal.workbench.faq_answer', wraps=faq_answer) as faq:
            report = app.execute_run(configuration)
        self.assertEqual([cid for cid, _ in seen], ['S01'] * 4 + ['S04'] * 4)
        self.assertEqual([call.args[1]['elapsed_days'] for call in faq.call_args_list], [20, 20])
        self.assertEqual([call.args[1]['delivered_on'] for call in faq.call_args_list],
                         ['2026-11-30', '2026-12-01'])
        self.assertTrue(all(set(data) == set(CustomerServiceAdapter.fields) for _, data in seen))
        self.assertEqual(report['configuration']['case_ids'], ['S01', 'S04'])
        self.assertEqual(configuration['case_ids'], ['S04', 'S01'])
        self.assertEqual([c['id'] for c in report['cases']], ['S01', 'S04'])
        self.assertEqual([c['id'] for c in report['api']['cases']], ['S01', 'S04'])
        self.assertEqual([c['id'] for c in report['faq']['cases']], ['S01', 'S04'])

    def test_subset_scope_and_manifest_pin_actual_executed_pack(self):
        app = self.require_app()
        configuration = {'faq_version': 'corrected', 'api_version': 'corrected',
                         'case_ids': ['S04', 'S01']}
        report = app.execute_run(configuration)
        expected = {'registered_total': 12, 'selected_total': 2,
                    'selected_case_ids': ['S01', 'S04'],
                    'omitted_case_ids': ['S02', 'S03', 'S05', 'S06', 'S07', 'S08',
                                         'S09', 'S10', 'S11', 'S12'], 'complete': False}
        self.assertEqual(report['scope'], expected)
        self.assertEqual(report['manifest']['scope'], expected)
        self.assertEqual(report['api']['scope'], expected)
        self.assertEqual(report['readiness'], 'PARTIAL_SCOPE')
        self.assertEqual(report['api']['readiness'], 'PARTIAL_SCOPE')
        self.assertEqual(report['total'], 2)
        self.assertEqual(report['counts'], {'PASS_WITHIN_SCOPE': 2})
        pack = app.load_packs(['customer_service'])[0]
        self.assertEqual(report['manifest']['registered_pack_sha256'], digest(pack))
        pack['cases'] = [c for c in pack['cases'] if c['id'] in ('S01', 'S04')]
        self.assertEqual(report['api']['manifest']['pack_digest'], digest(pack))
        self.assertEqual(report['manifest_sha256'], digest(report['manifest']))
        reordered = app.execute_run({**configuration, 'case_ids': ['S01', 'S04']})
        different = app.execute_run({**configuration, 'case_ids': ['S01']})
        self.assertEqual(report['manifest_sha256'], reordered['manifest_sha256'])
        self.assertNotEqual(report['manifest_sha256'], different['manifest_sha256'])

    def test_omitted_case_definition_remains_pinned_in_provenance(self):
        app = self.require_app()
        configuration = {'faq_version': 'corrected', 'api_version': 'corrected', 'case_ids': ['S04']}
        original = app.execute_run(configuration)
        pack = app.load_packs(['customer_service'])[0]
        pack['cases'][0]['label'] += ' (revised)'
        with patch('rehearsal.app.load_packs', return_value=[pack]):
            changed = app.execute_run(configuration)
        self.assertEqual(original['api']['manifest'], changed['api']['manifest'])
        self.assertNotEqual(original['manifest_sha256'], changed['manifest_sha256'])

    def test_explicit_full_selection_preserves_full_scope_and_legacy_results(self):
        app = self.require_app()
        configuration = {'faq_version': 'corrected', 'api_version': 'corrected'}
        legacy = app.execute_run(configuration)
        all_ids = [f'S{number:02d}' for number in range(1, 13)]
        explicit = app.execute_run({**configuration, 'case_ids': list(reversed(all_ids))})
        self.assertNotIn('case_ids', legacy['configuration'])
        self.assertEqual(explicit['configuration']['case_ids'], all_ids)
        self.assertEqual(explicit['cases'], legacy['cases'])
        self.assertEqual(legacy['scope'], explicit['scope'])
        self.assertEqual(explicit['scope']['omitted_case_ids'], [])
        self.assertTrue(explicit['scope']['complete'])
        self.assertEqual(explicit['readiness'], 'REVIEW_REQUIRED')

    def test_all_four_combinations_keep_failure_priority_inside_subset(self):
        app = self.require_app()
        for faq, api, failures in [('stale', 'stale', 1), ('corrected', 'stale', 1),
                                   ('stale', 'corrected', 1), ('corrected', 'corrected', 0)]:
            with self.subTest(faq=faq, api=api):
                report = app.execute_run({'faq_version': faq, 'api_version': api,
                                          'case_ids': ['S04', 'S10']})
                self.assertEqual(report['total'], 2)
                self.assertEqual(report['counts'].get('FAIL', 0), failures)
                self.assertEqual(report['counts'].get('INCONCLUSIVE'), 1)
                self.assertEqual(report['readiness'], 'BLOCKED' if failures else 'REVIEW_REQUIRED')
                self.assertFalse(report['scope']['complete'])

    def test_omitting_failures_and_unknowns_cannot_claim_full_readiness(self):
        app = self.require_app()
        report = app.execute_run({'faq_version': 'stale', 'api_version': 'stale', 'case_ids': ['S01']})
        self.assertEqual(report['counts'], {'PASS_WITHIN_SCOPE': 1})
        self.assertEqual(report['readiness'], 'PARTIAL_SCOPE')
        self.assertEqual(report['api']['readiness'], 'PARTIAL_SCOPE')
        self.assertIn('S04', report['scope']['omitted_case_ids'])
        self.assertIn('S10', report['scope']['omitted_case_ids'])

    def test_decision_summary_is_actual_response_not_expected_or_verdict(self):
        app = self.require_app()
        for faq, api in [('stale', 'stale'), ('corrected', 'stale'),
                          ('stale', 'corrected'), ('corrected', 'corrected')]:
            with self.subTest(faq=faq, api=api):
                case = app.execute_run({'faq_version': faq, 'api_version': api})['cases'][3]
                self.assertEqual(case.get('decision_summary'), {
                    'expected': {'status': 'DECIDED', 'decision': 'ELIGIBLE'},
                    'faq': {'status': 'DECIDED', 'decision': 'ELIGIBLE' if faq == 'corrected' else 'INELIGIBLE'},
                    'baseline_api': {'status': 'DECIDED', 'decision': 'INELIGIBLE'},
                    'candidate_api': {'status': 'DECIDED', 'decision': 'ELIGIBLE' if api == 'corrected' else 'INELIGIBLE'},
                })

    def test_state_summary_verifies_observed_payload_and_replay(self):
        case = self.require_app().execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})['cases'][3]
        self.assertEqual(case.get('state_summary'), {
            'expected_count': 1, 'observed_count': 1, 'replay_count': 1, 'verification': 'PASS',
            'checks': {'table': True, 'target': True, 'operation_key': True,
                       'input_digest': True, 'decision': True,
                       'preserved_state': True, 'replay_unchanged': True}, 'errors': [],
        })

    def test_matching_count_does_not_hide_wrong_observed_payload(self):
        app = self.require_app()
        for field, check in [('table', 'table'), ('target_id', 'target'),
                              ('operation_key', 'operation_key'), ('input_digest', 'input_digest'),
                              ('decision', 'decision')]:
            with self.subTest(field=field):
                class WrongPayload(CustomerServiceAdapter):
                    def _write(self, env, key, data, decision):
                        super()._write(env, key, data, decision)
                        if env.rows:
                            env.rows[-1][field] = 'wrong-value'
                with patch.dict(ADAPTERS, {'customer_service': WrongPayload}):
                    case = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})['cases'][3]
                self.assertIn('state_summary', case)
                state = case['state_summary']
                self.assertEqual(state['observed_count'], 1)
                self.assertEqual(state['replay_count'], 1)
                self.assertEqual(state['verification'], 'FAIL')
                self.assertIs(state['checks'][check], False)
                self.assertTrue(state['errors'])

    def test_observation_failure_is_null_not_zero_or_verified(self):
        app = self.require_app()
        with patch('rehearsal.engine.observe', side_effect=TimeoutError('cannot read')):
            report = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})
        for case in report['cases']:
            self.assertIn('state_summary', case)
            self.assertIsNone(case['state_summary']['observed_count'])
            self.assertIsNone(case['state_summary']['replay_count'])
            self.assertEqual(case['state_summary']['verification'], 'INCOMPLETE')
            self.assertTrue(all(value is None for value in case['state_summary']['checks'].values()))
            self.assertIsNone(case['decision_summary']['candidate_api'])
        self.assertEqual(report['readiness'], 'REVIEW_REQUIRED')

    def test_response_timeout_does_not_fabricate_replay_observation(self):
        app = self.require_app()
        class TimeoutAfterWrite(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                super().invoke(env, key, data)
                raise TimeoutError('response lost')
        with patch.dict(ADAPTERS, {'customer_service': TimeoutAfterWrite}):
            case = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})['cases'][3]
        self.assertIn('state_summary', case)
        self.assertEqual(case['state_summary']['observed_count'], 1)
        self.assertIsNone(case['state_summary']['replay_count'])
        self.assertIsNone(case['state_summary']['checks']['replay_unchanged'])
        self.assertEqual(case['state_summary']['verification'], 'INCOMPLETE')
        self.assertIsNone(case['decision_summary']['candidate_api'])

    def test_replay_read_failure_retains_first_observation_not_final_count(self):
        app = self.require_app()
        def fail_replay_read(env):
            if env.invocation_count == 2:
                raise TimeoutError('final read unavailable')
            return observe(env)
        with patch('rehearsal.engine.observe', side_effect=fail_replay_read):
            case = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})['cases'][3]
        self.assertIn('state_summary', case)
        self.assertEqual(case['state_summary']['observed_count'], 1)
        self.assertIsNone(case['state_summary']['replay_count'])
        self.assertIsNone(case['state_summary']['checks']['replay_unchanged'])
        self.assertEqual(case['state_summary']['verification'], 'INCOMPLETE')

    def test_invalid_faq_review_exposes_null_actual_decision(self):
        app = self.require_app()
        faq = app.load_json(app.ROOT / 'examples/customer_service/faq_corrected.json')
        faq['review']['content_sha256'] = '0' * 64
        with patch('rehearsal.app.load_json', return_value=faq):
            case = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})['cases'][3]
        self.assertIn('decision_summary', case)
        self.assertIsNone(case['decision_summary']['faq'])
        self.assertEqual(case['business_verdict'], 'INCONCLUSIVE')

    def test_engine_case_omission_or_reordering_cannot_silently_truncate_report(self):
        app = self.require_app()
        evaluate = app.evaluate_faq
        for mode in ('omit', 'reorder'):
            with self.subTest(mode=mode):
                def incomplete_faq(config, pack):
                    result = evaluate(config, pack)
                    result['cases'] = result['cases'][:-1] if mode == 'omit' else list(reversed(result['cases']))
                    return result
                with patch('rehearsal.app.evaluate_faq', side_effect=incomplete_faq), self.assertRaises(ValueError):
                    app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})

    def test_missing_response_field_is_null_and_not_a_successful_comparison(self):
        app = self.require_app()
        class MissingDecision(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                response = super().invoke(env, key, data)
                del response['decision']
                return response
        with patch.dict(ADAPTERS, {'customer_service': MissingDecision}):
            report = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})
        case = report['cases'][3]
        self.assertEqual(case['decision_summary']['candidate_api'], {'status': 'DECIDED', 'decision': None})
        self.assertEqual(case['state_summary']['verification'], 'FAIL')
        self.assertEqual(report['readiness'], 'BLOCKED')

    def test_snapshot_summary_detects_duplicate_replay_and_preserves_first_failure(self):
        app = self.require_app()
        class ReplayChangesState(CustomerServiceAdapter):
            def invoke(self, env, key, data):
                response = super().invoke(env, key, data)
                if env.invocation_count == 2:
                    self._write(env, key, data, response['decision'])
                return response
        with patch.dict(ADAPTERS, {'customer_service': ReplayChangesState}):
            case = app.execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})['cases'][3]
        self.assertEqual(case['state_summary']['observed_count'], 1)
        self.assertEqual(case['state_summary']['replay_count'], 2)
        self.assertIs(case['state_summary']['checks']['replay_unchanged'], False)
        self.assertEqual(case['state_summary']['verification'], 'FAIL')

    def test_no_effect_is_observed_but_row_identity_checks_are_not_applicable(self):
        case = self.require_app().execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})['cases'][0]
        self.assertEqual(case['state_summary']['observed_count'], 0)
        self.assertEqual(case['state_summary']['replay_count'], 0)
        self.assertEqual(case['state_summary']['verification'], 'PASS')
        self.assertIsNone(case['state_summary']['checks']['target'])
        self.assertIsNone(case['state_summary']['checks']['operation_key'])
        self.assertIs(case['state_summary']['checks']['preserved_state'], True)
        self.assertIs(case['state_summary']['checks']['replay_unchanged'], True)
