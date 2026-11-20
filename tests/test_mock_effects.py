import copy
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from rehearsal.adapters import CustomerServiceAdapter
from rehearsal.app import execute_run
from rehearsal.engine import run_pack
from rehearsal.policies import get_policy
from rehearsal.server import execute_persisted
from rehearsal.storage import EvidenceStore, ExecutionConflict, validate_report


class MockEffectsTests(unittest.TestCase):
    configuration = {'faq_version': 'corrected', 'api_version': 'corrected',
                     'policy_version': 'returns-20270115', 'case_ids': ['S01', 'S04']}

    def test_approved_mock_application_observes_zero_one_and_idempotent_repeat(self):
        report = execute_run(self.configuration)
        self.assertEqual(report['manifest']['effect_evidence_version'], 1)
        forbidden, allowed = report['cases']
        self.assertEqual(forbidden['candidate']['effects']['changes']['first'], {'REVIEWER': 0, 'CUSTOMER': 0})
        effect = allowed['candidate']['effects']
        self.assertEqual(allowed['baseline']['effects']['changes']['first']['REVIEWER'], 0)
        self.assertEqual(effect['changes']['first']['REVIEWER'], 1)
        self.assertEqual(effect['observations']['first'], effect['observations']['replay'])
        self.assertEqual(effect['findings'], [])
        validate_report(report)

    def test_duplicate_or_unseen_effect_is_never_a_pass_or_zero(self):
        policy = get_policy(self.configuration['policy_version'])
        run = run_pack(policy.load_pack(), 'duplicate_effect', policy_version=policy.identifier)
        duplicate = next(case for case in run['cases'] if case['id'] == 'S04')['candidate']
        self.assertEqual(duplicate['effects']['changes']['replay']['REVIEWER'], 2)
        self.assertIn('DUPLICATE', duplicate['effects']['findings'])
        self.assertIn('REPLAY_CHANGED', duplicate['effects']['findings'])
        with patch('rehearsal.engine.observe_intents', side_effect=TimeoutError):
            report = execute_run(self.configuration)
        candidate = report['cases'][1]['candidate']
        self.assertEqual(candidate['first_observed_state'][0]['table'], 'return_requests')
        self.assertIsNone(candidate['effects']['changes']['first'])
        self.assertEqual(candidate['effects']['findings'], ['UNCONFIRMED'])
        self.assertEqual(candidate['assertion_status'], 'INCOMPLETE')

    def test_saved_effect_rows_and_derived_counts_agree(self):
        report = execute_run(self.configuration)
        changed = copy.deepcopy(report)
        changed['cases'][1]['candidate']['effects']['changes']['first']['REVIEWER'] = 0
        with self.assertRaises(ValueError):
            validate_report(changed)
        changed = copy.deepcopy(report)
        changed['api']['cases'][1]['candidate']['effects']['observations']['first']['rows'][0]['role'] = 'CUSTOMER'
        with self.assertRaises(ValueError):
            validate_report(changed)
        old = execute_run({k: v for k, v in self.configuration.items() if k != 'policy_version'})
        self.assertNotIn('effects', old['cases'][0]['candidate'])
        validate_report(old)

    def test_wrong_role_exposes_the_missing_and_unexpected_role_independently(self):
        with patch.object(CustomerServiceAdapter, '_intent_role', return_value='CUSTOMER'):
            report = execute_run(self.configuration)
        candidate = report['cases'][1]['candidate']
        self.assertEqual(candidate['effects']['changes']['first'], {'REVIEWER': 0, 'CUSTOMER': 1})
        self.assertEqual(candidate['effects']['findings'], ['MISSING', 'WRONG_ROLE'])
        self.assertEqual(candidate['assertion_status'], 'FAIL')

    def test_process_death_after_mock_observation_keeps_only_committed_observation(self):
        script = '''
import os, sys
from rehearsal.app import execute_run
from rehearsal.server import execute_persisted
from rehearsal.storage import EvidenceStore
store = EvidenceStore(sys.argv[1])
record = store.record_stage
def checkpoint(attempt, key, stage, state, evidence):
    boundary = key.endswith(':candidate:decide') and stage == 'observation' and state == 'COMPLETED'
    if boundary and sys.argv[2] == 'before': os._exit(41)
    record(attempt, key, stage, state, evidence)
    if boundary: os._exit(42)
store.record_stage = checkpoint
execute_persisted(store, {'faq_version': 'corrected', 'api_version': 'corrected',
                          'policy_version': 'returns-20270115', 'case_ids': ['S04']},
                  execute_run, request_key='mock-effects-crash')
'''
        configuration = {**self.configuration, 'case_ids': ['S04']}
        with TemporaryDirectory(prefix='ax2-child-') as temporary:
            for boundary, exit_code in (('before', 41), ('after', 42)):
                with self.subTest(boundary=boundary):
                    workspace = Path(temporary) / boundary
                    child = subprocess.run([sys.executable, '-c', script, str(workspace), boundary],
                                           capture_output=True, text=True, timeout=30)
                    self.assertEqual(child.returncode, exit_code, child.stderr)
                    store = EvidenceStore(workspace)
                    attempt = store.list_attempts()[0]
                    self.assertTrue(attempt['confirmation_required'])
                    self.assertEqual(store.list_runs(), [])
                    checkpoint = attempt['stages'][-1]
                    self.assertEqual(checkpoint['stage'], 'observation')
                    if boundary == 'before':
                        self.assertEqual(checkpoint['state'], 'STARTED')
                        self.assertEqual(checkpoint['evidence'], {})
                    else:
                        observation = checkpoint['evidence']['value']['notification_intents']
                        self.assertEqual(checkpoint['state'], 'COMPLETED')
                        self.assertEqual(observation['state'], 'OBSERVED')
                        self.assertEqual([row['role'] for row in observation['rows']], ['REVIEWER'])
                    runner = Mock()
                    with self.assertRaises(ExecutionConflict):
                        execute_persisted(store, configuration, runner, request_key='mock-effects-crash')
                    runner.assert_not_called()
