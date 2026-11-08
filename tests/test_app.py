"""Product flow assertions remain separate from adapter/oracle implementation."""
import importlib.util
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch


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
