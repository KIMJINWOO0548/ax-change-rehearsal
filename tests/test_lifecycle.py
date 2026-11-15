"""Durable execution boundaries, using only synthetic reports and local files."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from rehearsal.storage import EvidenceStore, StorageConflict, StorageLimit
from rehearsal.recovery import create_backup, restore_backup
from tests.test_storage import report

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = EvidenceStore(self.root / 'active')
        self.config = {'faq_version': 'corrected', 'api_version': 'corrected'}

    def test_started_survives_restart_without_reexecution(self):
        attempt = self.store.begin_attempt(self.config)
        reopened = EvidenceStore(self.store.workspace)
        self.assertEqual(reopened.list_attempts()[0]['attempt_id'], attempt)
        self.assertEqual(reopened.list_attempts()[0]['state'], 'INCOMPLETE')
        self.assertEqual(reopened.list_runs(), [])

    def test_report_and_completion_are_atomic(self):
        attempt = self.store.begin_attempt(self.config)
        value = report(); value['configuration'] = self.config
        real_append = self.store._append
        def fail_finish(connection, payload):
            if payload['type'] == 'attempt_finished': raise OSError('synthetic disk fault')
            return real_append(connection, payload)
        with patch.object(self.store, '_append', side_effect=fail_finish):
            with self.assertRaises(Exception): self.store.save(value, attempt_id=attempt)
        self.assertEqual(self.store.list_runs(), [])
        self.assertEqual(self.store.list_attempts()[0]['state'], 'INCOMPLETE')
        self.store.save(value, attempt_id=attempt)
        self.assertEqual(self.store.list_attempts()[0]['state'], 'COMPLETED')
        with self.assertRaises(StorageConflict): self.store.fail_attempt(attempt)

    def test_backup_restores_incomplete_and_failed_without_retry(self):
        pending = self.store.begin_attempt(self.config)
        failed = self.store.begin_attempt(self.config)
        self.store.fail_attempt(failed)
        create_backup(self.store.workspace, self.root/'backup')
        restore_backup(self.root/'backup', self.root/'restored')
        restored = EvidenceStore(self.root/'restored')
        states = {x['attempt_id']: x['state'] for x in restored.list_attempts()}
        self.assertEqual(states, {pending:'INCOMPLETE', failed:'FAILED'})

    def test_full_store_rejects_before_execution(self):
        store = EvidenceStore(self.store.workspace, limit=1)
        store.save(report())
        with self.assertRaises(StorageLimit): store.begin_attempt(self.config)
        self.assertEqual(store.list_attempts(), [])

    def test_server_execution_records_start_before_runner_and_failure(self):
        from rehearsal.server import execute_persisted
        def failed(configuration):
            self.assertEqual(self.store.list_attempts()[0]['state'], 'INCOMPLETE')
            raise RuntimeError('synthetic execution failure')
        with self.assertRaises(RuntimeError): execute_persisted(self.store, self.config, failed)
        self.assertEqual(self.store.list_attempts()[0]['state'], 'FAILED')
        self.assertEqual(self.store.list_runs(), [])

    def test_server_execution_binds_report(self):
        from rehearsal.server import execute_persisted
        def successful(configuration):
            value = report(); value['configuration'] = configuration
            return value
        result = execute_persisted(self.store, self.config, successful)
        self.assertEqual(result['record']['run_id'], self.store.list_attempts()[0]['run_id'])
        self.assertEqual(self.store.list_attempts()[0]['state'], 'COMPLETED')

    def test_mismatched_report_rolls_back(self):
        attempt = self.store.begin_attempt(self.config)
        value = report(); value['configuration'] = {'faq_version':'stale','api_version':'stale'}
        with self.assertRaises(Exception): self.store.save(value, attempt_id=attempt)
        self.assertEqual(self.store.list_runs(), [])
        self.assertEqual(self.store.list_attempts()[0]['state'], 'INCOMPLETE')

    def test_start_at_ledger_limit_is_rejected_without_damaging_store(self):
        with patch('rehearsal.storage.MAX_LEDGER_ROWS', 0):
            with self.assertRaises(StorageLimit): self.store.begin_attempt(self.config)
        self.assertEqual(self.store.list_attempts(), [])

    def test_pending_attempt_reserves_capacity(self):
        store = EvidenceStore(self.store.workspace, limit=1)
        attempt = store.begin_attempt(self.config)
        with self.assertRaises(StorageLimit): store.begin_attempt(self.config)
        with self.assertRaises(StorageLimit): store.save(report())
        store.fail_attempt(attempt)
        self.assertIsInstance(store.begin_attempt(self.config), str)

    def test_successful_runner_with_save_failure_remains_incomplete(self):
        from rehearsal.server import execute_persisted
        value=report(); value['configuration']=self.config
        with patch.object(self.store, 'save', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError): execute_persisted(self.store, self.config, lambda _: value)
        self.assertEqual(self.store.list_attempts()[0]['state'],'INCOMPLETE')

    def test_concurrent_capacity_reservation_has_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        store=EvidenceStore(self.store.workspace, limit=1)
        def begin(_):
            try: return store.begin_attempt(self.config)
            except StorageLimit: return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            winners=[x for x in pool.map(begin,range(4)) if x is not None]
        self.assertEqual(len(winners),1)
        self.assertEqual(len(store.list_attempts()),1)

    def test_older_report_cannot_complete_a_later_attempt(self):
        from rehearsal.storage import StorageError
        value=report();value['configuration']=self.config
        self.store.save(value)
        attempt=self.store.begin_attempt(self.config)
        with self.assertRaises(StorageError):
            self.store._operate(lambda connection,runs: self.store._finish(connection,attempt,'COMPLETED',value['run_id']))
        self.assertEqual(self.store.list_attempts()[0]['state'],'INCOMPLETE')
        self.assertEqual(len(self.store.list_runs()),1)

    def test_hash_valid_but_chronologically_invalid_history_is_rejected(self):
        from rehearsal.storage import StorageError
        value=report();value['configuration']=self.config
        self.store.save(value)
        attempt=self.store.begin_attempt(self.config)
        self.store._operate(lambda connection,runs: self.store._append(connection,{
            'type':'attempt_finished','attempt_id':attempt,'state':'COMPLETED',
            'run_id':value['run_id'],'created_at':value['created_at']}))
        with self.assertRaises(StorageError):EvidenceStore(self.store.workspace)

    def test_process_death_during_save_rolls_back_partial_report(self):
        import subprocess,sys,textwrap
        from unittest.mock import Mock
        from rehearsal.server import execute_persisted
        from rehearsal.storage import ExecutionConflict
        script=textwrap.dedent('''
            import os,sys
            from rehearsal.storage import EvidenceStore
            from rehearsal.server import execute_persisted
            from tests.test_storage import report
            store=EvidenceStore(sys.argv[1])
            append=store._append
            def interrupted(connection,payload):
                append(connection,payload)
                if payload['type']=='run': os._exit(29)
            store._append=interrupted
            def runner(config):
                value=report();value['configuration']=config;return value
            execute_persisted(store,{'faq_version':'corrected','api_version':'corrected'},runner,request_key='crash-save')
        ''')
        child=subprocess.run([sys.executable,'-c',script,str(self.store.workspace)],capture_output=True,timeout=20)
        self.assertEqual(child.returncode,29,child.stderr)
        reopened=EvidenceStore(self.store.workspace)
        self.assertEqual(reopened.list_runs(),[])
        self.assertEqual(reopened.list_attempts()[0]['state'],'INCOMPLETE')
        runner=Mock()
        with self.assertRaises(ExecutionConflict):execute_persisted(reopened,self.config,runner,request_key='crash-save')
        runner.assert_not_called()
        create_backup(reopened.workspace,self.root/'crash-backup')
        restore_backup(self.root/'crash-backup',self.root/'crash-restored')
        restored=EvidenceStore(self.root/'crash-restored')
        self.assertEqual(restored.list_runs(),[])
        self.assertEqual(restored.list_attempts()[0]['state'],'INCOMPLETE')

    def test_process_death_after_commit_replays_without_reexecution(self):
        import subprocess,sys,textwrap
        from unittest.mock import Mock
        from rehearsal.server import execute_persisted
        script=textwrap.dedent('''
            import os,sys
            from rehearsal.storage import EvidenceStore
            from rehearsal.server import execute_persisted
            from tests.test_storage import report
            store=EvidenceStore(sys.argv[1])
            save=store.save
            def interrupted(value,**kwargs):
                save(value,**kwargs)
                os._exit(31)
            store.save=interrupted
            def runner(config):
                value=report();value['configuration']=config;return value
            execute_persisted(store,{'faq_version':'corrected','api_version':'corrected'},runner,request_key='crash-response')
        ''')
        child=subprocess.run([sys.executable,'-c',script,str(self.store.workspace)],capture_output=True,timeout=20)
        self.assertEqual(child.returncode,31,child.stderr)
        reopened=EvidenceStore(self.store.workspace)
        self.assertEqual(reopened.list_attempts()[0]['state'],'COMPLETED')
        runner=Mock()
        result=execute_persisted(reopened,self.config,runner,request_key='crash-response')
        runner.assert_not_called()
        self.assertEqual(result['run_id'],reopened.list_attempts()[0]['run_id'])
        self.assertEqual(len(reopened.list_runs()),1)
