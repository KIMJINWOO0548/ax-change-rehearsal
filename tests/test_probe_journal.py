import tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from rehearsal.storage import EvidenceStore, ExecutionConflict, StorageError
from rehearsal.probe_journal import execute_probe
from rehearsal.recovery import create_backup, restore_backup

class ProbeJournalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.store=EvidenceStore(self.root/'active')
 def runner(self,port,**kwargs):
  self.assertEqual(self.store.list_attempts()[0]['state'],'INCOMPLETE')
  return {'synthetic_only':True,'scope':'disposable-loopback-probe','status':'CANCELLED',
          'dispatch':'NOT_STARTED','remote_effects':'UNKNOWN','local_cleanup_verified':True,
          'response':None,'events':['PREPARED','CANCELLED_BEFORE_START']}
 def test_record_and_replay_after_restart_and_backup(self):
  runner=Mock(side_effect=self.runner)
  a=execute_probe(self.store,12345,request_key='intent',runner=runner)
  self.assertEqual(self.store.list_attempts()[0]['state'],'RECORDED')
  self.assertEqual(self.store.list_runs(),[])
  create_backup(self.store.workspace,self.root/'archive');restore_backup(self.root/'archive',self.root/'restore')
  b=execute_probe(EvidenceStore(self.root/'restore'),12345,request_key='intent',runner=runner)
  self.assertEqual(a,b);self.assertEqual(runner.call_count,1)
 def test_pending_never_reexecutes_and_changed_port_conflicts(self):
  runner=Mock(side_effect=OSError('unconfirmed'))
  with self.assertRaises(OSError):execute_probe(self.store,12345,request_key='intent',runner=runner)
  for port in (12345,12346):
   with self.assertRaises(ExecutionConflict):execute_probe(self.store,port,request_key='intent',runner=runner)
  self.assertEqual(runner.call_count,1)
 def test_save_failure_stays_incomplete(self):
  runner=Mock(side_effect=self.runner)
  with patch.object(self.store,'record_probe',side_effect=StorageError('disk')):
   with self.assertRaises(StorageError):execute_probe(self.store,12345,request_key='intent',runner=runner)
  self.assertEqual(self.store.list_attempts()[0]['state'],'INCOMPLETE')
  with self.assertRaises(ExecutionConflict):execute_probe(self.store,12345,request_key='intent',runner=runner)
  self.assertEqual(runner.call_count,1)
 def test_invalid_outcome_is_not_recorded_as_success(self):
  runner=Mock(return_value={'status':'COMPLETED','remote_effects':'NONE'})
  with self.assertRaises(ValueError):execute_probe(self.store,12345,request_key='intent',runner=runner)
  self.assertEqual(self.store.list_attempts()[0]['state'],'INCOMPLETE')

 def test_concurrent_claim_reserves_one_probe(self):
  from concurrent.futures import ThreadPoolExecutor
  config={'kind':'disposable-loopback-probe','port':12345,'timeout':5}
  with ThreadPoolExecutor(max_workers=8) as pool:
   results=list(pool.map(lambda _: EvidenceStore(self.store.workspace).claim_probe(config,'same'),range(8)))
  self.assertEqual(sum(claimed for attempt,claimed in results),1)
  self.assertEqual(len({a['attempt_id'] for a,_ in results}),1)
 def test_business_attempt_cannot_be_finished_as_probe(self):
  attempt=self.store.begin_attempt({'faq_version':'stale','api_version':'stale'})
  with self.assertRaises(StorageError):self.store.record_probe(attempt,self.runner(12345))
  self.assertEqual(self.store.list_attempts()[0]['state'],'INCOMPLETE')
 def test_inconsistent_lifecycle_and_response_binding_rejected(self):
  from rehearsal.probe_journal import validate_outcome
  base=self.runner(12345) if self.store.list_attempts() else {'synthetic_only':True,'scope':'disposable-loopback-probe','status':'CANCELLED','dispatch':'NOT_STARTED','remote_effects':'UNKNOWN','local_cleanup_verified':True,'response':None,'events':['PREPARED','CANCELLED_BEFORE_START']}
  for changed in ({'status':'COMPLETED'}, {'dispatch':'SENT'}, {'local_cleanup_verified':False}, {'events':['PREPARED','COMPLETED']}):
   with self.subTest(changed=changed),self.assertRaises(ValueError):validate_outcome({**base,**changed},'a'*32)

 def test_incomplete_probe_blocks_rollover(self):
  from rehearsal.recovery import rollover_workspace, RecoveryError
  with self.assertRaises(OSError):execute_probe(self.store,12345,request_key='pending',runner=Mock(side_effect=OSError('unknown')))
  with self.assertRaises(RecoveryError):rollover_workspace(self.store.workspace,self.root/'archive',self.root/'next')
 def test_failed_and_timedout_outcomes_are_recorded_not_success(self):
  for status in ('FAILED','TIMED_OUT','CLEANUP_FAILED'):
   outcome={'synthetic_only':True,'scope':'disposable-loopback-probe','status':status,'dispatch':'SENT',
            'remote_effects':'UNKNOWN','local_cleanup_verified':status!='CLEANUP_FAILED','response':None,
            'events':['PREPARED','WORKER_STARTED','CONNECTING','REQUEST_SENT',status]}
   runner=Mock(return_value=outcome)
   first=execute_probe(self.store,12345,request_key=status,runner=runner)
   second=execute_probe(self.store,12345,request_key=status,runner=runner)
   self.assertEqual(first,second);self.assertEqual(runner.call_count,1)
   self.assertEqual(second['status'],status);self.assertEqual(self.store.list_attempts()[0]['state'],'RECORDED')
