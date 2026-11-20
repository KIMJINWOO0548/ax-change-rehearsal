"""Atomic sealed publication checks using synthetic ciphertext only."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from rehearsal import sealed


@unittest.skipUnless(os.name == 'nt', 'Windows exclusive publication')
class WindowsSealedPublicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.target = self.root / 'backup.ax'

    def test_publication_does_not_require_hardlinks(self):
        with patch.object(sealed.os, 'link', side_effect=PermissionError('hardlinks unavailable')):
            sealed._publish(self.target, b'header-', b'complete ciphertext')
        self.assertEqual(self.target.read_bytes(), b'header-complete ciphertext')
        self.assertEqual(self.target.stat().st_nlink, 1)
        self.assertFalse(list(self.root.glob('.sealed-*')))

    def test_destination_created_at_flush_is_never_overwritten(self):
        original = os.fsync
        def flush_then_create(fd):
            original(fd)
            with self.target.open('xb') as file:
                file.write(b'other writer')
        with patch.object(sealed.os, 'fsync', side_effect=flush_then_create):
            with self.assertRaises(FileExistsError):
                sealed._publish(self.target, b'header-', b'complete ciphertext')
        self.assertEqual(self.target.read_bytes(), b'other writer')
        self.assertFalse(list(self.root.glob('.sealed-*')))

    def test_process_exit_around_publish_cannot_leave_partial_destination(self):
        for boundary in ('before', 'after'):
            with self.subTest(boundary=boundary):
                target = self.root / (boundary + '.ax')
                code = """
from pathlib import Path
import os, sys
from rehearsal import sealed
target = Path(sys.argv[1])
if sys.argv[2] == 'before':
    original = os.fsync
    def crash(fd):
        original(fd)
        os._exit(81)
    sealed.os.fsync = crash
else:
    sealed.recovery._sync_directory = lambda _: os._exit(82)
sealed._publish(target, b'header-', b'complete ciphertext')
"""
                result = subprocess.run([sys.executable, '-c', code, str(target), boundary],
                                        capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 81 if boundary == 'before' else 82,
                                 result.stderr.decode(errors='replace'))
                if boundary == 'before':
                    self.assertFalse(target.exists())
                    staging, = self.root.glob('.sealed-*')
                    self.assertEqual(staging.read_bytes(), b'header-complete ciphertext')
                    staging.unlink()
                else:
                    self.assertEqual(target.read_bytes(), b'header-complete ciphertext')
                    self.assertFalse(list(self.root.glob('.sealed-*')))
