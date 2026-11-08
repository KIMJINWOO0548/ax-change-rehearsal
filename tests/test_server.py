"""Real loopback HTTP tests: hostile websites must not execute local work."""
import http.client
import importlib.util
import json
import threading
import unittest
from unittest.mock import patch


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = None
        if importlib.util.find_spec('rehearsal.server') is not None:
            from rehearsal.server import make_server
            cls.server = make_server(0)
            cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
            cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join(timeout=3)

    def request(self, method='GET', path='/api/context', body=None, headers=None):
        self.assertIsNotNone(self.server, 'Local HTTP workbench is not implemented')
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request(method,path,body=body,headers=headers or {})
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        connection.close()
        return result

    def token(self):
        status, _, data = self.request()
        self.assertEqual(status,200)
        return json.loads(data)['csrf_token']

    def post(self, data=None, **headers):
        headers = {'Content-Type':'application/json', 'X-CSRF-Token':self.token(), **headers}
        return self.request('POST','/api/run', data if data is not None else json.dumps({'faq_version':'corrected','api_version':'corrected'}), headers)

    def test_context_and_live_run(self):
        status,headers,data=self.post()
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data)['counts'],{'PASS_WITHIN_SCOPE':9,'INCONCLUSIVE':3})
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertNotIn('Access-Control-Allow-Origin',headers)

    def test_http_subset_returns_canonical_scope_and_manifest(self):
        configuration = {'faq_version': 'corrected', 'api_version': 'corrected',
                         'case_ids': ['S04', 'S01']}
        status, _, body = self.post(json.dumps(configuration))
        self.assertEqual(status, 200)
        report = json.loads(body)
        self.assertEqual(report['configuration']['case_ids'], ['S01', 'S04'])
        self.assertEqual(report['scope']['registered_total'], 12)
        self.assertEqual(report['scope']['selected_total'], 2)
        self.assertFalse(report['scope']['complete'])
        self.assertEqual(report['manifest']['scope'], report['scope'])
        self.assertEqual(report['readiness'], 'PARTIAL_SCOPE')
        self.assertEqual([case['id'] for case in report['cases']], ['S01', 'S04'])
        self.assertEqual(report['cases'][1]['state_summary']['verification'], 'PASS')

    def test_http_case_selection_rejects_invalid_types_duplicates_and_unknowns(self):
        for ids in (None, [], 'S04', {}, [True], [4], [None], [['S04']], [{}],
                    ['s04'], [' S04'], ['S13'], ['S04', 'S04'], ['S04'] * 13):
            with self.subTest(ids=ids):
                status, _, body = self.post(json.dumps({
                    'faq_version': 'corrected', 'api_version': 'corrected', 'case_ids': ids}))
                self.assertEqual(status, 400)
                self.assertIn('error', json.loads(body))

    def test_http_subset_duplicate_json_key_is_rejected(self):
        status, _, _ = self.post('{"faq_version":"corrected","api_version":"corrected",'
                                 '"case_ids":["S01"],"case_ids":["S04"]}')
        self.assertEqual(status, 400)

    def test_http_all_four_subset_combinations_keep_unknowns(self):
        for faq, api, readiness in [('stale', 'stale', 'BLOCKED'),
                                    ('corrected', 'stale', 'BLOCKED'),
                                    ('stale', 'corrected', 'BLOCKED'),
                                    ('corrected', 'corrected', 'REVIEW_REQUIRED')]:
            with self.subTest(faq=faq, api=api):
                status, _, body = self.post(json.dumps({
                    'faq_version': faq, 'api_version': api, 'case_ids': ['S04', 'S10']}))
                self.assertEqual(status, 200)
                report = json.loads(body)
                self.assertEqual(report['readiness'], readiness)
                self.assertEqual(report['counts']['INCONCLUSIVE'], 1)
                self.assertFalse(report['scope']['complete'])

    def test_forged_hosts_are_rejected_before_context_or_run(self):
        for host in ('evil.example','127.0.0.1.evil.example','localhost','127.0.0.1:1'):
            with self.subTest(host=host):
                self.assertEqual(self.request(headers={'Host':host})[0],403)

    def test_foreign_origins_and_fetch_metadata_are_rejected(self):
        for headers in ({'Origin':'https://evil.example'}, {'Origin':'null'},
                        {'Origin':'http://localhost:1'}, {'Sec-Fetch-Site':'cross-site'},
                        {'Sec-Fetch-Site':'same-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.post(**headers)[0],403)

    def test_same_origin_is_accepted(self):
        self.token()
        status,_,_=self.post(Origin=f'http://127.0.0.1:{self.server.server_port}', **{'Sec-Fetch-Site':'same-origin'})
        self.assertEqual(status,200)

    def test_missing_wrong_or_duplicate_token_rejected(self):
        body=json.dumps({'faq_version':'stale','api_version':'stale'})
        for headers in ({'Content-Type':'application/json'},
                        {'Content-Type':'application/json','X-CSRF-Token':'wrong'}):
            self.assertEqual(self.request('POST','/api/run',body,headers)[0],403)

    def test_non_ascii_token_is_rejected_without_connection_failure(self):
        status,_,body=self.post(**{'X-CSRF-Token':'é'})
        self.assertEqual(status,403)
        self.assertEqual(json.loads(body)['error']['code'],'SESSION_REQUIRED')

    def test_duplicate_security_headers_rejected(self):
        token=self.token()
        for duplicate in ('Host','X-CSRF-Token','Origin','Content-Length'):
            connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
            connection.putrequest('POST','/api/run',skip_host=True)
            base={'Host':f'127.0.0.1:{self.server.server_port}', 'Content-Type':'application/json',
                  'X-CSRF-Token':token,'Content-Length':'0',
                  'Origin':f'http://127.0.0.1:{self.server.server_port}'}
            for key,value in base.items():
                connection.putheader(key,value)
                if key==duplicate:
                    connection.putheader(key,value)
            connection.endheaders()
            response=connection.getresponse()
            with self.subTest(header=duplicate):
                self.assertIn(response.status,(400,403))
            response.read()
            connection.close()

    def test_malformed_ambiguous_or_large_body_rejected(self):
        for body in ('{','[]','null','{"faq_version":"stale","faq_version":"corrected","api_version":"stale"}',
                     '{"faq_version":NaN,"api_version":"stale"}',
                     '{"faq_version":"stale","api_version":"stale","unknown":1}'):
            with self.subTest(body=body):
                self.assertEqual(self.post(body)[0],400)
        self.assertEqual(self.post('x'*2049)[0],413)
        self.assertEqual(self.post(**{'Content-Type':'text/plain'})[0],415)

    def test_chunked_transfer_encoding_rejected(self):
        self.assertEqual(self.post(**{'Transfer-Encoding':'chunked'})[0],400)

    def test_static_paths_cannot_expose_source_or_tokens(self):
        for path in ('/../README.md','/%2e%2e/README.md','/rehearsal/server.py','/web/','/.git/config','/api/context?callback=x'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path=path)[0],404)

    def test_unexpected_error_does_not_expose_traceback_or_paths(self):
        self.token()
        with patch('rehearsal.server.execute_run',side_effect=RuntimeError('private/path/secret')):
            status,_,body=self.post()
        self.assertEqual(status,500)
        self.assertNotIn(b'private',body)
        self.assertNotIn(b'Traceback',body)
