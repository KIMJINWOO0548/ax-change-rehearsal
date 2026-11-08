from contextlib import closing
"""Durability, integrity and concurrent optimistic review tests with synthetic reports."""
import concurrent.futures
import copy
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from rehearsal.storage import EvidenceStore, StorageError, StorageConflict, StorageLimit, RunNotFound, sha


def report():
    return {'run_id': uuid.uuid4().hex, 'created_at': '2026-01-01T00:00:00+00:00',
            'synthetic_only': True, 'scope': {'complete': False, 'selected_case_ids': ['S01']},
            'readiness': 'PARTIAL_SCOPE', 'configuration': {'case_ids': ['S01']}, 'counts': {'PASS_WITHIN_SCOPE': 1}}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'evidence'
        self.store = EvidenceStore(self.path)
        self.report = report()
        self.record = self.store.save(self.report)

    def payload(self, **changes):
        return {'expected_revision': 0, 'report_sha256': self.record['sha256'],
                'status': 'REVIEWED', 'note': '합성 검토', **changes}

    def test_restart_preserves_exact_report_scope_and_review(self):
        original = copy.deepcopy(self.report)
        detail = self.store.review(self.report['run_id'], self.payload())
        reopened = EvidenceStore(self.path)
        self.assertEqual(reopened.get(self.report['run_id']), detail)
        self.assertEqual(detail['report'], original)
        self.assertEqual(detail['record']['sha256'], sha(original))
        self.assertFalse(detail['record']['review_is_approval'])
        self.assertEqual(detail['record']['revision'], 1)
        self.assertEqual(reopened.list_runs()[0]['readiness'], 'PARTIAL_SCOPE')
        self.assertEqual(self.report, original)

    def test_mismatch_never_appends(self):
        for changes in ({'expected_revision': 1}, {'report_sha256': 'f'*64}):
            with self.assertRaises(StorageConflict):
                self.store.review(self.report['run_id'], self.payload(**changes))
        self.assertEqual(self.store.get(self.report['run_id'])['events'], [])

    def test_concurrent_review_only_one_wins(self):
        def review(_):
            try:
                self.store.review(self.report['run_id'], self.payload())
                return 'saved'
            except StorageConflict:
                return 'conflict'
        with concurrent.futures.ThreadPoolExecutor(4) as executor:
            results = list(executor.map(review, range(4)))
        self.assertEqual(results.count('saved'), 1)
        self.assertEqual(results.count('conflict'), 3)
        self.assertEqual(len(self.store.get(self.report['run_id'])['events']), 1)

    def test_run_limit_no_eviction(self):
        store = EvidenceStore(self.path, limit=1)
        with self.assertRaises(StorageLimit): store.save(report())
        self.assertEqual(len(store.list_runs()), 1)

    def test_unknown_id(self):
        for action in (lambda: self.store.get('a'*32), lambda: self.store.review('a'*32, self.payload())):
            with self.assertRaises(RunNotFound): action()

    def test_invalid_review_rejected(self):
        for changes in ({'expected_revision': True}, {'status': 'APPROVED'}, {'note': 'x'*1001},
                        {'note': None}, {'report_sha256': 'bad'}, {'identity': 'someone'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.review(self.report['run_id'], self.payload(**changes))

    def test_tampering_fails_every_operation_and_restart(self):
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute("UPDATE ledger SET payload=replace(payload,'PARTIAL_SCOPE','APPROVED') WHERE seq=1")
        for action in (self.store.list_runs, lambda: self.store.get(self.report['run_id']),
                       lambda: self.store.save(report()), lambda: self.store.review(self.report['run_id'], self.payload()),
                       lambda: EvidenceStore(self.path)):
            with self.assertRaises(StorageError): action()

    def test_deleted_tail_detected_against_metadata(self):
        self.store.review(self.report['run_id'], self.payload())
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute('DELETE FROM ledger WHERE seq=2')
        with self.assertRaises(StorageError): self.store.list_runs()

    def test_corrupt_database_not_recreated(self):
        self.store.path.write_bytes(b'corrupt')
        with self.assertRaises(StorageError): EvidenceStore(self.path)
        self.assertEqual(self.store.path.read_bytes(), b'corrupt')

    @unittest.skipUnless(os.name == 'posix', 'POSIX permissions')
    def test_private_paths_and_reject_permissive_or_symlink(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        link = Path(self.temp.name) / 'link'; link.symlink_to(self.path)
        with self.assertRaises(StorageError): EvidenceStore(link)
        os.chmod(self.path, 0o755)
        with self.assertRaises(StorageError): EvidenceStore(self.path)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o755)
        os.chmod(self.path, 0o700)

    def test_database_symlink_rejected(self):
        target = Path(self.temp.name) / 'copy'; self.store.path.rename(target)
        try:
            self.store.path.symlink_to(target)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege unavailable")
            raise
        with self.assertRaises(StorageError): self.store.list_runs()

    def test_database_hardlink_rejected(self):
        target = Path(self.temp.name) / "copy"
        self.store.path.rename(target)
        os.link(target, self.store.path)
        with self.assertRaises(StorageError): self.store.list_runs()

    def test_failed_connection_configuration_closes_connection(self):
        from unittest.mock import patch, Mock
        connection = Mock()
        connection.execute.side_effect = sqlite3.DatabaseError('corrupt')
        with patch('rehearsal.storage.sqlite3.connect', return_value=connection):
            with self.assertRaises(StorageError):
                self.store.list_runs()
        connection.close.assert_called_once_with()
