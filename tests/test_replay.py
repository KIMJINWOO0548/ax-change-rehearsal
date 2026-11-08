"""Conservative replay and imported-source drift regression tests."""
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rehearsal.app import execute_run
from rehearsal.replay import replay_report


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.report = execute_run({'faq_version': 'corrected', 'api_version': 'corrected'})

    def test_identical_synthetic_evidence_matches_but_unknowns_stay_unknown(self):
        result = replay_report(self.report)
        self.assertEqual(result['status'], 'MATCH')
        self.assertEqual(result['counts']['INCONCLUSIVE'], 3)
        self.assertFalse(result['deployment_approval'])

    def test_partial_scope_is_preserved(self):
        report = execute_run({'faq_version': 'stale', 'api_version': 'corrected', 'case_ids': ['S04']})
        self.assertEqual(replay_report(report)['status'], 'MATCH')
        self.assertFalse(replay_report(report)['scope']['complete'])

    def test_modified_observed_evidence_does_not_match(self):
        self.report['cases'][0]['reason'] = 'changed evidence'
        self.assertEqual(replay_report(self.report)['status'], 'DIFFERENT')

    def test_missing_or_invalid_proof_fails_closed_before_execution(self):
        variants = []
        for key in ['synthetic_only', 'manifest', 'manifest_sha256', 'scope', 'cases']:
            changed = copy.deepcopy(self.report)
            changed.pop(key)
            variants.append(changed)
        changed = copy.deepcopy(self.report)
        changed['configuration']['faq_version'] = 'stale'
        variants.append(changed)
        for report in variants:
            with self.subTest(report=list(report)), patch('rehearsal.replay.execute_run') as run:
                with self.assertRaises(ValueError):
                    replay_report(report)
                run.assert_not_called()

    def test_changed_source_or_policy_is_not_a_reproducibility_pass(self):
        from rehearsal.adapters import digest
        self.report['manifest']['service_sources']['rehearsal/app.py'] = '0' * 64
        self.report['manifest_sha256'] = digest(self.report['manifest'])
        self.assertEqual(replay_report(self.report)['status'], 'INCOMPATIBLE')

    def test_non_synthetic_report_is_rejected(self):
        self.report['synthetic_only'] = False
        with self.assertRaises(ValueError):
            replay_report(self.report)

    def test_code_changed_after_package_import_blocks_manifest_and_run(self):
        import shutil
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            shutil.copytree(root / 'rehearsal', tmp / 'rehearsal')
            shutil.copytree(root / 'fixtures', tmp / 'fixtures')
            script = """from rehearsal.engine import load_packs, run_pack
from pathlib import Path
p = Path('rehearsal/adapters.py')
p.write_bytes(p.read_bytes() + b'\\n# changed after import\\n')
try:
    run_pack(load_packs(['customer_service'])[0])
except RuntimeError as error:
    assert str(error) == 'Execution sources changed; restart and review before running.'
else:
    raise AssertionError('source drift must block execution')
"""
            done = subprocess.run([sys.executable, '-c', script], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_input_changes_during_execution_are_rejected(self):
        import shutil
        root = Path(__file__).resolve().parents[1]
        for changed in ('fixtures/customer_service/policy_after.md',
                        'fixtures/customer_service/pack.json',
                        'examples/customer_service/faq_corrected.json'):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                tmp = Path(directory)
                for name in ('rehearsal', 'fixtures', 'examples'):
                    shutil.copytree(root / name, tmp / name)
                script = '''import rehearsal.app as app
from pathlib import Path
original = app.run_pack
def mutate(pack, variant):
    path = Path(%r)
    path.write_bytes(path.read_bytes() + b'\\n ')
    return original(pack, variant)
app.run_pack = mutate
try:
    app.execute_run({'faq_version':'corrected','api_version':'corrected'})
except ValueError as error:
    assert str(error) == 'Execution inputs changed; restart and review before running.'
else:
    raise AssertionError('input drift must block the report')
''' % changed
                done = subprocess.run([sys.executable, '-c', script], cwd=tmp, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
