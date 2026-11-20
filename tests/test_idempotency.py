import tempfile, unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from rehearsal.storage import EvidenceStore, StorageConflict
from rehearsal.server import execute_persisted
from tests.test_storage import report

class IdempotencyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'store'; self.store=EvidenceStore(self.path)
  self.config={'faq_version':'corrected','api_version':'corrected'}
 def runner(self):
  value=report(); value['configuration']=self.config
  return Mock(return_value=value)
 def test_retry_after_restart_returns_same_result(self):
  runner=self.runner()
  a=execute_persisted(self.store,self.config,runner,request_key='retry-1')
  b=execute_persisted(EvidenceStore(self.path),self.config,runner,request_key='retry-1')
  self.assertEqual(a,b); self.assertEqual(runner.call_count,1)
 def test_changed_configuration_conflicts(self):
  execute_persisted(self.store,self.config,self.runner(),request_key='retry-1')
  with self.assertRaises(StorageConflict):
   execute_persisted(self.store,{**self.config,'faq_version':'stale'},self.runner(),request_key='retry-1')
 def test_pending_and_failed_never_rerun(self):
  item,new=self.store.claim_attempt(self.config,'retry-1'); self.assertTrue(new)
  runner=self.runner()
  with self.assertRaises(StorageConflict): execute_persisted(self.store,self.config,runner,request_key='retry-1')
  self.store.fail_attempt(item['attempt_id'])
  with self.assertRaises(StorageConflict): execute_persisted(self.store,self.config,runner,request_key='retry-1')
  runner.assert_not_called()
 def test_concurrent_claim_is_unique(self):
  with ThreadPoolExecutor(max_workers=8) as pool:
   values=list(pool.map(lambda _: EvidenceStore(self.path).claim_attempt(self.config,'shared'),range(8)))
  self.assertEqual(sum(new for item,new in values),1)
  self.assertEqual(len({item['attempt_id'] for item,new in values}),1)
 def test_invalid_keys_rejected(self):
  for key in ('','x'*129,'space key','한글',7):
   with self.subTest(key=key),self.assertRaises(ValueError): self.store.claim_attempt(self.config,key)

 def test_selection_order_matches_canonical_report(self):
  from rehearsal.app import execute_run
  config={**self.config,'case_ids':['S04','S01']}
  first=execute_persisted(self.store,config,execute_run,request_key='selection')
  second=execute_persisted(self.store,{**config,'case_ids':['S01','S04']},self.runner(),request_key='selection')
  self.assertEqual(first,second)
