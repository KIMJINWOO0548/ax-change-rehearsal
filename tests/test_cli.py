import json
import os
from pathlib import Path
import subprocess
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
