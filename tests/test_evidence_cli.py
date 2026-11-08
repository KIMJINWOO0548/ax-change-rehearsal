import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from manage_evidence import main
from rehearsal.app import execute_run
from rehearsal.storage import EvidenceStore


class EvidenceCliTests(unittest.TestCase):
    def test_verify_list_replay_do_not_mutate_saved_record_or_approve(self):
        with tempfile.TemporaryDirectory() as parent:
            workspace = Path(parent) / 'evidence'
            store = EvidenceStore(workspace)
            report = execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})
            store.save(report)
            for args in (['verify'], ['list'], ['replay', report['run_id']]):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = main(['--workspace', str(workspace), *args])
                self.assertEqual(code, 0)
                self.assertFalse(json.loads(out.getvalue())['deployment_approval'])
            self.assertEqual(store.get(report['run_id'])['record']['revision'], 0)
            self.assertEqual(len(store.list_runs()), 1)

    def test_missing_workspace_does_not_create_or_leak_path(self):
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / 'private-missing'
            error = io.StringIO()
            with contextlib.redirect_stderr(error):
                code = main(['--workspace', str(target), 'verify'])
            self.assertEqual(code, 1)
            self.assertFalse(target.exists())
            self.assertNotIn(str(target), error.getvalue())

    def test_corrupt_workspace_replay_is_never_a_match(self):
        with tempfile.TemporaryDirectory() as parent:
            workspace = Path(parent) / 'evidence'
            store = EvidenceStore(workspace)
            report = execute_run({'faq_version': 'stale', 'api_version': 'stale'})
            store.save(report)
            store.path.write_bytes(b'broken')
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--workspace', str(workspace), 'replay', report['run_id']]), 1)
