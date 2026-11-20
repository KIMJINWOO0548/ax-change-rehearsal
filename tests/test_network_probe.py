"""Disposable service tests; no business system is contacted."""
import json, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from rehearsal.network_probe import probe

class ProbeTests(unittest.TestCase):
 def setUp(self):
  self.requests=[]; self.finished=threading.Event(); self.delay=.8; owner=self
  class Handler(BaseHTTPRequestHandler):
   def do_GET(self):
    owner.requests.append(self.path)
    if owner.mode=='disconnect':
     self.close_connection=True;return
    if owner.mode=='slow': time.sleep(owner.delay)
    body=json.dumps({'synthetic_only':True,'probe_id':self.headers['X-Probe-ID'],'value':'ok'}).encode()
    if owner.mode=='oversize': body=b'x'*9000
    owner.finished.set()
    try:
     self.send_response(302 if owner.mode=='redirect' else 200)
     self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    except OSError:pass
   def log_message(self,*args):pass
  self.mode='ok';self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
  self.server.daemon_threads=True
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.thread.join(2)
 def test_complete_has_observation_and_cleanup(self):
  result=probe(self.server.server_port,timeout=5)
  self.assertEqual(result['status'],'COMPLETED');self.assertTrue(result['local_cleanup_verified'])
  self.assertEqual(result['remote_effects'],'UNKNOWN');self.assertEqual(len(self.requests),1)
  self.assertEqual(result['response']['value'],'ok')
 def test_deadline_stops_local_worker_not_remote_work(self):
  self.mode='slow'; self.delay=3; result=probe(self.server.server_port,timeout=2)
  self.assertEqual(result['status'],'TIMED_OUT',result);self.assertTrue(result['local_cleanup_verified'])
  self.assertEqual(result['dispatch'],'SENT',result)
  self.assertEqual(result['remote_effects'],'UNKNOWN');self.assertIsNone(result['response'])
 def test_precancel_sends_nothing(self):
  cancel=threading.Event();cancel.set();result=probe(self.server.server_port,cancel=cancel)
  self.assertEqual(result['status'],'CANCELLED');self.assertEqual(self.requests,[])
  self.assertEqual(result['dispatch'],'NOT_STARTED')
 def test_cancel_after_dispatch_stops_local_worker(self):
  self.mode='slow';cancel=threading.Event()
  def trigger():
   deadline=time.monotonic()+5
   while not self.requests and time.monotonic()<deadline:time.sleep(.01)
   cancel.set()
  t=threading.Thread(target=trigger);t.start()
  result=probe(self.server.server_port,timeout=6,cancel=cancel);t.join(6)
  self.assertEqual(result['status'],'CANCELLED',result);self.assertTrue(result['local_cleanup_verified'])
  self.assertEqual(result['remote_effects'],'UNKNOWN')
  self.assertTrue(self.finished.wait(2),'Remote fixture can continue after local cancellation')
 def test_redirect_and_oversize_fail_closed(self):
  for mode in ('redirect','oversize'):
   self.mode=mode;result=probe(self.server.server_port,timeout=5)
   self.assertEqual(result['status'],'FAILED');self.assertIsNone(result['response'])
   self.assertTrue(result['local_cleanup_verified'])
 def test_invalid_arguments(self):
  for port in (True,0,65536,'80'):
   with self.assertRaises(ValueError):probe(port)

 def test_peer_failure_is_preserved_not_relabelled_as_late_cancel(self):
  self.mode='disconnect';cancel=threading.Event()
  result=probe(self.server.server_port,timeout=5,cancel=cancel)
  cancel.set()
  self.assertEqual(result['status'],'FAILED',result)
  self.assertEqual(result['error']['stage'],'READ_RESPONSE',result)
  self.assertIn(result['error']['type'],('RemoteDisconnected','ConnectionResetError'))
  self.assertTrue(result['local_cleanup_verified'])
  self.assertEqual(result['remote_effects'],'UNKNOWN')

 def test_real_probe_is_recorded_and_retry_does_not_resend(self):
  import tempfile
  from rehearsal.storage import EvidenceStore
  from rehearsal.probe_journal import execute_probe
  with tempfile.TemporaryDirectory() as directory:
   store=EvidenceStore(directory)
   first=execute_probe(store,self.server.server_port,request_key='real-probe')
   self.assertEqual(first['status'],'COMPLETED',first)
   second=execute_probe(EvidenceStore(directory),self.server.server_port,request_key='real-probe')
   self.assertEqual(first,second);self.assertEqual(len(self.requests),1)
   item=store.list_attempts()[0]
   self.assertEqual(item['state'],'RECORDED');self.assertEqual(item['type'],'probe_started')
   self.assertEqual(first['response']['probe_id'],item['attempt_id'])


 def test_cancelled_durable_probe_replays_unknown_without_resending(self):
  import tempfile
  from rehearsal.storage import EvidenceStore
  from rehearsal.probe_journal import execute_probe
  self.mode='slow';cancel=threading.Event()
  def trigger():
   deadline=time.monotonic()+5
   while not self.requests and time.monotonic()<deadline:time.sleep(.01)
   cancel.set()
  t=threading.Thread(target=trigger);t.start()
  with tempfile.TemporaryDirectory() as directory:
   store=EvidenceStore(directory)
   first=execute_probe(store,self.server.server_port,request_key='cancelled',timeout=6,cancel=cancel)
   t.join(6)
   self.assertEqual(first['status'],'CANCELLED',first)
   self.assertEqual(first['remote_effects'],'UNKNOWN')
   second=execute_probe(EvidenceStore(directory),self.server.server_port,request_key='cancelled',timeout=6)
   self.assertEqual(second,first);self.assertEqual(len(self.requests),1)
   self.assertEqual(store.list_attempts()[0]['state'],'RECORDED')
  self.assertTrue(self.finished.wait(2))


class FailureEvidenceTests(unittest.TestCase):
 def test_connect_error_retains_os_codes_without_raw_exception(self):
  from unittest.mock import patch
  from rehearsal.network_probe import _worker
  class Channel:
   def __init__(self):self.items=[]
   def send(self,value):self.items.append(value)
   def close(self):pass
  channel=Channel();error=OSError(14,'private diagnostic text');error.winerror=10014
  with patch('rehearsal.network_probe.http.client.HTTPConnection',side_effect=error):
   _worker(channel,12345,'nonce',1)
  self.assertEqual(channel.items[-1],('failure',{'type':'OSError','stage':'CONNECT_OR_SEND','errno':14,'winerror':10014}))
  self.assertNotIn('private diagnostic',json.dumps(channel.items))

 def test_queued_failure_is_drained_before_cancellation(self):
  from unittest.mock import Mock, patch
  from collections import deque
  errors={'type':'OSError','stage':'CONNECT_OR_SEND','errno':14,'winerror':10014}
  messages=deque([('stage','CONNECTING'),('failure',errors)])
  receiver=Mock();receiver.poll.side_effect=lambda timeout: bool(messages)
  receiver.recv.side_effect=messages.popleft
  sender=Mock();worker=Mock();worker.is_alive.return_value=False
  context=Mock();context.Pipe.return_value=(receiver,sender);context.Process.return_value=worker
  cancel=Mock();cancel.is_set.side_effect=[False,True]
  with patch('rehearsal.network_probe.multiprocessing.get_context',return_value=context):
   result=probe(12345,cancel=cancel)
  self.assertEqual(result['status'],'FAILED');self.assertEqual(result['error'],errors)

 def test_late_queued_response_is_not_completion(self):
  from unittest.mock import Mock, patch
  receiver=Mock();receiver.poll.return_value=True;receiver.recv.return_value=('result',{'value':'ok'})
  worker=Mock();worker.is_alive.return_value=False
  context=Mock();context.Pipe.return_value=(receiver,Mock());context.Process.return_value=worker
  with patch('rehearsal.network_probe.multiprocessing.get_context',return_value=context),patch('rehearsal.network_probe.time.monotonic',side_effect=[0,10,10]):
   result=probe(12345,timeout=5)
  self.assertEqual(result['status'],'TIMED_OUT');self.assertIsNone(result['response'])
  self.assertEqual(result['terminal_observed'],'RESPONSE_AFTER_BUDGET')

class CleanupRecoveryTests(unittest.TestCase):
 def exercise(self, survives):
  from unittest.mock import Mock, patch
  receiver=Mock();receiver.poll.return_value=False
  worker=Mock();worker.is_alive.side_effect=lambda: survives or not worker.kill.called
  worker.terminate.side_effect=OSError('private cleanup failure')
  context=Mock();context.Pipe.return_value=(receiver,Mock());context.Process.return_value=worker
  cancel=Mock();cancel.is_set.side_effect=[False,True]
  with patch('rehearsal.network_probe.multiprocessing.get_context',return_value=context):
   result=probe(12345,cancel=cancel)
  return result,worker
 def test_termination_error_still_attempts_kill(self):
  result,worker=self.exercise(False)
  worker.kill.assert_called_once()
  self.assertEqual(result['status'],'CANCELLED')
  self.assertTrue(result['local_cleanup_verified'])
  self.assertEqual(result['remote_effects'],'UNKNOWN')
 def test_surviving_worker_records_cleanup_failure(self):
  from rehearsal.probe_journal import validate_outcome
  result,worker=self.exercise(True)
  worker.kill.assert_called_once()
  self.assertEqual(result['status'],'CLEANUP_FAILED')
  self.assertFalse(result['local_cleanup_verified'])
  validate_outcome(result,'a'*32)
  self.assertNotIn('private cleanup failure',json.dumps(result))
 def test_kill_error_is_durably_recorded_and_never_resent(self):
  import tempfile
  from unittest.mock import Mock, patch
  from rehearsal.storage import EvidenceStore
  from rehearsal.probe_journal import execute_probe
  receiver=Mock();receiver.poll.return_value=False
  worker=Mock();worker.is_alive.return_value=True
  worker.terminate.side_effect=OSError('terminate');worker.kill.side_effect=OSError('kill')
  context=Mock();context.Pipe.return_value=(receiver,Mock());context.Process.return_value=worker
  cancel=Mock();cancel.is_set.side_effect=[False,True]
  with tempfile.TemporaryDirectory() as directory,patch('rehearsal.network_probe.multiprocessing.get_context',return_value=context):
   first=execute_probe(EvidenceStore(directory),12345,request_key='cleanup',cancel=cancel)
   second=execute_probe(EvidenceStore(directory),12345,request_key='cleanup')
   self.assertEqual(first,second)
   self.assertEqual(first['status'],'CLEANUP_FAILED')
   self.assertFalse(first['local_cleanup_verified'])
   context.Process.assert_called_once()
   worker.close.assert_not_called()
 def test_late_response_cleanup_failure_remains_valid_evidence(self):
  from rehearsal.probe_journal import validate_outcome
  from unittest.mock import Mock, patch
  from collections import deque
  messages=deque([('stage','CONNECTING'),('stage','REQUEST_SENT'),('result',{'value':'ok'})])
  receiver=Mock();receiver.poll.side_effect=lambda timeout: bool(messages);receiver.recv.side_effect=messages.popleft
  worker=Mock();worker.is_alive.return_value=True
  context=Mock();context.Pipe.return_value=(receiver,Mock());context.Process.return_value=worker
  with patch('rehearsal.network_probe.multiprocessing.get_context',return_value=context),patch('rehearsal.network_probe.time.monotonic',side_effect=[0,10,10]):
   result=probe(12345,timeout=5)
  self.assertEqual(result['status'],'CLEANUP_FAILED')
  self.assertEqual(result['terminal_observed'],'RESPONSE_AFTER_BUDGET')
  self.assertIsNone(result['response'])
  validate_outcome(result,'a'*32)


class DeadlineStageTests(unittest.TestCase):
 """Deterministic parent-loop checks, not evidence of real socket dispatch."""
 def exercise_expired_budget(self, stages):
  from collections import deque
  from unittest.mock import Mock, patch
  messages=deque(('stage', value) for value in stages)
  receiver=Mock();receiver.poll.side_effect=lambda timeout: bool(messages)
  receiver.recv.side_effect=messages.popleft
  worker=Mock();worker.is_alive.return_value=False
  context=Mock();context.Pipe.return_value=(receiver,Mock());context.Process.return_value=worker
  # The same total deadline applies even if process startup consumed the budget.
  with patch('rehearsal.network_probe.multiprocessing.get_context',return_value=context),patch('rehearsal.network_probe.time.monotonic',side_effect=[0,3,3]):
   result=probe(12345,timeout=2)
  self.assertEqual(result['status'],'TIMED_OUT')
  self.assertTrue(result['local_cleanup_verified'])
  self.assertEqual(result['remote_effects'],'UNKNOWN')
  self.assertIsNone(result['response'])
  worker.start.assert_called_once();worker.close.assert_called_once()
  from rehearsal.probe_journal import validate_outcome
  validate_outcome(result,'a'*32)
  return result
 def test_startup_deadline_does_not_invent_dispatch(self):
  result=self.exercise_expired_budget([])
  self.assertEqual(result['dispatch'],'UNKNOWN')
  self.assertEqual(result['events'],['PREPARED','WORKER_STARTED','TIMED_OUT'])
 def test_connecting_deadline_does_not_invent_dispatch(self):
  result=self.exercise_expired_budget(['CONNECTING'])
  self.assertEqual(result['dispatch'],'UNKNOWN')
  self.assertNotIn('REQUEST_SENT',result['events'])
 def test_sent_stage_is_preserved_at_deadline(self):
  result=self.exercise_expired_budget(['CONNECTING','REQUEST_SENT'])
  self.assertEqual(result['dispatch'],'SENT')
  self.assertEqual(result['events'],['PREPARED','WORKER_STARTED','CONNECTING','REQUEST_SENT','TIMED_OUT'])
