"""Local recovery CLI acceptance tests with synthetic data only."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from manage_recovery import main
from rehearsal.app import execute_run
from rehearsal.storage import EvidenceStore


class RecoveryCliTests(unittest.TestCase):
    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_backup_inspect_restore_roundtrip_and_safe_output(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent)
            store = EvidenceStore(root / 'original')
            report = execute_run({'faq_version': 'corrected', 'api_version': 'corrected', 'case_ids': ['S04', 'S10']})
            record = store.save(report)
            store.review(report['run_id'], {'expected_revision': 0, 'report_sha256': record['sha256'],
                                           'status': 'CHANGES_REQUESTED', 'note': 'Synthetic note that must not appear in CLI output'})
            before = store.get(report['run_id'])
            commands = [
                ['backup', '--workspace', str(root / 'original'), '--destination', str(root / 'backup')],
                ['inspect', '--source', str(root / 'backup')],
                ['restore', '--source', str(root / 'backup'), '--destination', str(root / 'restored')],
            ]
            outputs = []
            for command in commands:
                code, output, error = self.invoke(command)
                self.assertEqual(code, 0, error)
                self.assertEqual(error, '')
                result = json.loads(output)
                self.assertEqual(result['status'], 'VERIFIED')
                self.assertFalse(result['deployment_approval'])
                self.assertFalse(result['encrypted'])
                self.assertFalse(result['authenticated'])
                self.assertNotIn('Synthetic note', output)
                self.assertNotIn(str(root), output)
                self.assertNotIn('configuration', result)
                outputs.append(result)
            self.assertEqual(len({result['database_sha256'] for result in outputs}), 1)
            restored = EvidenceStore(root / 'restored')
            self.assertEqual(restored.get(report['run_id']), before)
            self.assertEqual(store.get(report['run_id']), before)

    def test_missing_source_never_creates_destination_or_leaks_path(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent)
            for operation, flag in [('backup', '--workspace'), ('restore', '--source')]:
                code, output, error = self.invoke([operation, flag, str(root / 'private-missing'),
                                                  '--destination', str(root / operation)])
                self.assertEqual(code, 1)
                self.assertEqual(output, '')
                self.assertNotIn(str(root), error)
                self.assertFalse((root / operation).exists())

    def test_inspect_error_has_no_success_or_traceback(self):
        with tempfile.TemporaryDirectory() as parent:
            code, output, error = self.invoke(['inspect', '--source', parent])
            self.assertEqual(code, 1)
            self.assertEqual(output, '')
            self.assertEqual(json.loads(error)['error'], 'RECOVERY_UNAVAILABLE')
            self.assertNotIn('Traceback', error)

    def test_restore_never_overwrites_existing_destination(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent)
            EvidenceStore(root / 'original')
            self.assertEqual(self.invoke(['backup', '--workspace', str(root / 'original'),
                                         '--destination', str(root / 'backup')])[0], 0)
            target = root / 'existing'; target.mkdir()
            sentinel = target / 'user-data'; sentinel.write_text('preserve')
            code, output, _ = self.invoke(['restore', '--source', str(root / 'backup'), '--destination', str(target)])
            self.assertEqual(code, 1)
            self.assertEqual(output, '')
            self.assertEqual(sentinel.read_text(), 'preserve')
            self.assertEqual(list(target.iterdir()), [sentinel])
