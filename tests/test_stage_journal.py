"""Synthetic operation checkpoints survive process death without resuming work."""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rehearsal.app import execute_run
from rehearsal.engine import stage_recorder
from rehearsal.recovery import create_backup, restore_backup
from rehearsal.server import execute_persisted
from rehearsal.storage import EvidenceStore, ExecutionConflict, StorageError, StorageLimit


class StageJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {'faq_version': 'corrected', 'api_version': 'corrected', 'case_ids': ['S02']}

    def test_forced_exit_before_and_after_invocation_and_observation_commit(self):
        script = textwrap.dedent('''
            import os, sys
            from rehearsal.app import execute_run
            from rehearsal.server import execute_persisted
            from rehearsal.storage import EvidenceStore
            store = EvidenceStore(sys.argv[1])
            record = store.record_stage
            def checkpoint(attempt, key, stage, state, evidence):
                selected = stage == sys.argv[2] and state == 'COMPLETED'
                if selected and sys.argv[3] == 'before': os._exit(41)
                record(attempt, key, stage, state, evidence)
                if selected: os._exit(42)
            store.record_stage = checkpoint
            execute_persisted(store, {'faq_version':'corrected','api_version':'corrected','case_ids':['S02']},
                              execute_run, request_key='crash-stage')
        ''')
        for stage in ('invocation', 'observation'):
            for boundary in ('before', 'after'):
                with self.subTest(stage=stage, boundary=boundary):
                    workspace = self.root / (stage + '-' + boundary)
                    child = subprocess.run([sys.executable, '-c', script, str(workspace), stage, boundary],
                                           capture_output=True, text=True, timeout=30)
                    print(f'forced_exit stage={stage} boundary={boundary} exit={child.returncode} '
                          f'stdout={child.stdout!r} stderr={child.stderr!r}')
                    self.assertEqual(child.returncode, 41 if boundary == 'before' else 42, child.stderr)
                    store = EvidenceStore(workspace)
                    attempt = store.list_attempts()[0]
                    self.assertEqual(attempt['state'], 'INCOMPLETE')
                    self.assertTrue(attempt['confirmation_required'])
                    self.assertEqual(store.list_runs(), [])
                    checkpoint = attempt['stages'][-1]
                    self.assertEqual(checkpoint['stage'], stage)
                    self.assertEqual(checkpoint['state'], 'STARTED' if boundary == 'before' else 'COMPLETED')
                    if boundary == 'after': self.assertIn('value', checkpoint['evidence'])
                    runner = Mock()
                    with self.assertRaises(ExecutionConflict):
                        execute_persisted(store, self.config, runner, request_key='crash-stage')
                    runner.assert_not_called()
                    create_backup(workspace, self.root / (stage + boundary + '-backup'))
                    restore_backup(self.root / (stage + boundary + '-backup'), self.root / (stage + boundary + '-restore'))
                    self.assertEqual(EvidenceStore(self.root / (stage + boundary + '-restore')).list_attempts(), [attempt])

    def test_stage_capacity_reserved_before_operation(self):
        store = EvidenceStore(self.root / 'active')
        with patch('rehearsal.storage.MAX_LEDGER_ROWS', 4):
            with self.assertRaises(StorageLimit): execute_persisted(store, self.config, execute_run)
        self.assertEqual(store.list_attempts()[0]['state'], 'FAILED')
        self.assertNotIn('stages', store.list_attempts()[0])
        self.assertIsNone(stage_recorder.get())

    def test_stage_order_and_terminal_row_reservations(self):
        store = EvidenceStore(self.root / 'active')
        attempt = store.begin_attempt(self.config)
        with self.assertRaises(StorageError): store.record_stage(attempt, 'key', 'invocation', 'STARTED', {})
        with patch('rehearsal.storage.MAX_LEDGER_ROWS', 5):
            store.record_stage(attempt, 'key', 'initial_observation', 'STARTED', {})
            with self.assertRaises(StorageLimit): store.begin_attempt(self.config)
            store.record_stage(attempt, 'key', 'initial_observation', 'COMPLETED', {'value': []})
            with self.assertRaises(StorageError):
                store.record_stage(attempt, 'key', 'initial_observation', 'COMPLETED', {'value': []})
            store.fail_attempt(attempt)
        self.assertEqual(len(store.list_attempts()[0]['stages']), 1)

    def test_timeout_and_cancel_preserve_failed_invocation(self):
        from rehearsal.adapters import CustomerServiceAdapter
        for failure in (TimeoutError, KeyboardInterrupt):
            with self.subTest(failure=failure.__name__):
                store = EvidenceStore(self.root / failure.__name__)
                with patch.object(CustomerServiceAdapter, 'invoke', side_effect=failure('synthetic interruption')):
                    if failure is KeyboardInterrupt:
                        with self.assertRaises(KeyboardInterrupt): execute_persisted(store, self.config, execute_run)
                    else:
                        result = execute_persisted(store, self.config, execute_run)
                        self.assertNotEqual(result['readiness'], 'PASS_WITHIN_REGISTERED_SCOPE')
                attempt = EvidenceStore(store.workspace).list_attempts()[0]
                invocations = [s for s in attempt['stages'] if s['stage'] == 'invocation']
                self.assertTrue(invocations)
                self.assertTrue(all(s['state'] == 'FAILED' for s in invocations))
                self.assertTrue(attempt['confirmation_required'])
                self.assertIsNone(stage_recorder.get())
