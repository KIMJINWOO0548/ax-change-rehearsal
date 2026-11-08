import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WorkbenchCliTests(unittest.TestCase):
    def test_legacy_console_encoding_preserves_utf8_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, PYTHONIOENCODING='cp1252')
            result = subprocess.run(
                [sys.executable, str(ROOT / 'run_workbench.py'), '--output', directory],
                cwd=ROOT, env=env, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('cp1252', errors='replace'))
            self.assertIn('REVIEW_REQUIRED', result.stdout.decode('cp1252'))
            report = json.loads((Path(directory) / 'workbench.json').read_text(encoding='utf-8'))
            self.assertIn('수정', report['stages'][-1]['title'])
            self.assertTrue((Path(directory) / 'index.html').is_file())

    def test_demo_legacy_console_with_unicode_project_path(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / '합성-project'
            project.mkdir()
            shutil.copy2(ROOT / 'run_demo.py', project)
            for name in ('rehearsal', 'fixtures'):
                shutil.copytree(ROOT / name, project / name, ignore=shutil.ignore_patterns('__pycache__'))
            result = subprocess.run(
                [sys.executable, str(project / 'run_demo.py')], cwd=project,
                env=dict(os.environ, PYTHONIOENCODING='cp1252'), capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('cp1252', errors='replace'))
            self.assertIn('Synthetic mocks only', result.stdout.decode('cp1252'))
            report = json.loads((project / 'results' / 'rehearsal_results.json').read_text(encoding='utf-8'))
            self.assertTrue(report['summaries'])
