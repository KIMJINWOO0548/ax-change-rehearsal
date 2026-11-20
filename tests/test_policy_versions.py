import copy,tempfile,unittest
import hashlib
from pathlib import Path
from unittest.mock import patch,Mock
from rehearsal.app import execute_run
from rehearsal.adapters import canonical
from rehearsal.policies import get_policy,VERSIONS
from rehearsal.replay import replay_report
from rehearsal.server import execute_persisted
from rehearsal.storage import EvidenceStore,ExecutionConflict

class PolicyVersionTests(unittest.TestCase):
 def test_every_adapter_uses_a_separate_pinned_policy_artifact(self):
  from rehearsal.engine import ROOT, load_packs, run_pack
  versions = [(pack, None, f"fixtures/{pack['pack_id']}/mock_policy.json") for pack in load_packs()]
  versions.append((get_policy('returns-20270115').load_pack(), 'returns-20270115',
                   'fixtures/customer_service/versions/returns-20270115/mock_policy.json'))
  for pack, version, path in versions:
   with self.subTest(path=path):
    result = run_pack(pack, policy_version=version)
    self.assertIn(path, result['manifest']['sources'])
    self.assertEqual(result['manifest']['sources'][path], hashlib.sha256((ROOT / path).read_bytes()).hexdigest())
    self.assertEqual(result['counts'].get('FAIL', 0), 0)

 def test_changed_adapter_policy_is_refused_before_invocation(self):
  from rehearsal.engine import load_packs, run_pack
  pack = load_packs(['manufacturing'])[0]
  original = Path.read_text
  def changed(path, *args, **kwargs):
   value = original(path, *args, **kwargs)
   return value+' ' if path.as_posix().endswith('manufacturing/mock_policy.json') else value
  with patch.object(Path,'read_text',changed), patch('rehearsal.engine.run_side') as run:
   with self.assertRaises(ValueError):
    run_pack(pack)
   run.assert_not_called()

 def config(self,version='returns-20270115'):
  return dict(faq_version='corrected',api_version='corrected',policy_version=version)
 def test_distinct_policy_dates_and_explicit_boundaries(self):
  old=execute_run(self.config('returns-20261201'));new=execute_run(self.config())
  self.assertEqual(old['api']['manifest']['policy_version'],'returns-20261201')
  self.assertEqual(new['api']['manifest']['policy_version'],'returns-20270115')
  self.assertEqual(new['counts'],{'PASS_WITHIN_SCOPE':8})
  self.assertEqual([c['candidate']['response']['decision'] for c in new['cases']],['INELIGIBLE','ELIGIBLE','ELIGIBLE','ELIGIBLE','INELIGIBLE','ELIGIBLE','INELIGIBLE','INELIGIBLE'])
  self.assertEqual(new['faq']['content']['effective_date'],'2027-01-15')
  self.assertNotEqual(old['manifest_sha256'],new['manifest_sha256'])
 def test_registry_and_old_policy_are_immutable(self):
  before=canonical(execute_run(self.config('returns-20261201'))['cases'])
  with self.assertRaises(TypeError):VERSIONS['new']=None
  with self.assertRaises(AttributeError):get_policy('returns-20261201').new_window_days=999
  altered=get_policy('returns-20270115').load_pack();altered['cases'].clear()
  execute_run(self.config())
  self.assertEqual(before,canonical(execute_run(self.config('returns-20261201'))['cases']))
 def test_legacy_default_and_saved_replay_survive_new_selection(self):
  legacy=execute_run(dict(faq_version='corrected',api_version='corrected'))
  with tempfile.TemporaryDirectory() as folder:
   store=EvidenceStore(folder);store.save(legacy)
   execute_persisted(store,self.config(),execute_run,request_key='v3')
   restored=EvidenceStore(folder).get(legacy['run_id'])['report']
   self.assertEqual(replay_report(restored)['status'],'MATCH')
 def test_version_bound_replay_and_retry(self):
  with tempfile.TemporaryDirectory() as folder:
   store=EvidenceStore(folder);runner=Mock(side_effect=execute_run)
   first=execute_persisted(store,self.config(),runner,request_key='same')
   again=execute_persisted(EvidenceStore(folder),self.config(),runner,request_key='same')
   self.assertEqual(first,again);self.assertEqual(runner.call_count,1)
   self.assertEqual(replay_report(first)['status'],'MATCH')
   with self.assertRaises(ExecutionConflict):execute_persisted(store,self.config('returns-20261201'),runner,request_key='same')
 def test_interruption_cannot_reexecute_another_policy(self):
  with tempfile.TemporaryDirectory() as folder:
   store=EvidenceStore(folder);store.claim_attempt(self.config(),'pending')
   for version in VERSIONS:
    runner=Mock()
    with self.assertRaises(ExecutionConflict):execute_persisted(EvidenceStore(folder),self.config(version),runner,request_key='pending')
    runner.assert_not_called()
 def test_unknown_version_never_executes(self):
  for bad in ('../other',None,True,'latest'):
   with self.assertRaises(ValueError):execute_run(self.config(bad))
 def test_stale_and_wrong_date_variants_are_detected(self):
  from rehearsal.engine import run_pack
  pack=get_policy('returns-20270115').load_pack()
  for variant in ('stale_candidate','wrong_effective_scope','boundary','exception_removed'):
   self.assertGreater(run_pack(pack,variant,policy_version='returns-20270115')['counts'].get('FAIL',0),0)
 def test_pinned_artifact_drift_is_rejected_before_execution(self):
  from pathlib import Path
  original=Path.read_text
  # Directly target the registered pack while preserving all other source reads.
  target=get_policy('returns-20270115').pack_path
  def changed(path,*args,**kwargs):
   value=original(path,*args,**kwargs)
   return value+' ' if path.as_posix().endswith(target) else value
  with patch.object(Path,'read_text',changed),patch('rehearsal.app.run_pack') as run:
   with self.assertRaises(ValueError):execute_run(self.config())
   run.assert_not_called()
 def test_cross_version_pack_and_mutated_oracle_are_rejected(self):
  from rehearsal.engine import run_pack
  pack=get_policy('returns-20270115').load_pack()
  with self.assertRaises(ValueError):run_pack(pack,policy_version='returns-20261201')
  pack['cases'][0]['expected_after']['decision']='ELIGIBLE'
  with self.assertRaises(ValueError):run_pack(pack,policy_version='returns-20270115')
 def test_selected_case_order_and_scope_remain_bound(self):
  config={**self.config(),'case_ids':['S04','S01']}
  result=execute_run(config)
  self.assertEqual(result['scope']['selected_case_ids'],['S01','S04'])
  self.assertEqual(result['readiness'],'PARTIAL_SCOPE')
  self.assertEqual(replay_report(result)['status'],'MATCH')
 def test_registry_manifest_tampering_never_matches(self):
  from rehearsal.adapters import digest
  result=execute_run(self.config())
  result['manifest']['api_manifest']['policy_version']='returns-20261201'
  result['manifest_sha256']=digest(result['manifest'])
  self.assertEqual(replay_report(result)['status'],'INCOMPATIBLE')
 def test_backup_restore_retains_both_versions(self):
  from pathlib import Path
  from rehearsal.recovery import create_backup,restore_backup
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);store=EvidenceStore(root/'active')
   results=[execute_persisted(store,self.config(v),execute_run,request_key=v) for v in VERSIONS]
   create_backup(store.workspace,root/'backup');restore_backup(root/'backup',root/'restored')
   restored=EvidenceStore(root/'restored')
   for result in results:
    saved=restored.get(result['run_id'])['report']
    self.assertEqual(saved['configuration'],result['configuration'])
    self.assertEqual(replay_report(saved)['status'],'MATCH')
 def test_old_source_evidence_remains_readable_but_not_false_match(self):
  from rehearsal.adapters import digest
  result=execute_run(dict(faq_version='corrected',api_version='corrected'))
  result['manifest']['service_sources']['rehearsal/app.py']='0'*64
  result['manifest_sha256']=digest(result['manifest'])
  with tempfile.TemporaryDirectory() as folder:
   store=EvidenceStore(folder);store.save(result)
   saved=EvidenceStore(folder).get(result['run_id'])['report']
   self.assertEqual(saved,result)
   self.assertEqual(replay_report(saved)['status'],'INCOMPATIBLE')
 def test_direct_engine_rechecks_artifacts_after_execution(self):
  from pathlib import Path
  from rehearsal import engine
  original_read=Path.read_text;original_run=engine.run_side;changed=[False]
  target=get_policy('returns-20270115').faq_root+'/faq_corrected.json'
  def read(path,*args,**kwargs):
   value=original_read(path,*args,**kwargs)
   return value+' ' if changed[0] and path.as_posix().endswith(target) else value
  def run(*args,**kwargs):
   result=original_run(*args,**kwargs);changed[0]=True;return result
  pack=get_policy('returns-20270115').load_pack()
  with patch.object(Path,'read_text',read),patch.object(engine,'run_side',run):
   with self.assertRaises(ValueError):engine.run_pack(pack,policy_version='returns-20270115')
