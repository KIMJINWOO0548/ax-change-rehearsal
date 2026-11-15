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
