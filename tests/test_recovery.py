"""Offline recovery bundles preserve evidence, never interpret imported data."""
import concurrent.futures
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from rehearsal.storage import EvidenceStore
from rehearsal.recovery import create_backup, inspect_backup, restore_backup, RecoveryError
from tests.test_storage import report


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.backup = self.root / 'backup'
        self.target = self.root / 'restored'
        self.store = EvidenceStore(self.workspace)
        self.report = report()
        record = self.store.save(self.report)
        self.detail = self.store.review(self.report['run_id'], {
            'expected_revision': 0, 'report_sha256': record['sha256'],
            'status': 'CHANGES_REQUESTED', 'note': 'synthetic private note'})

    def bundle(self):
        return create_backup(self.workspace, self.backup)

    def update_checksum(self):
        path = self.backup / 'manifest.json'
        data = json.loads(path.read_text())
        data['database_sha256'] = hashlib.sha256((self.backup / 'evidence.sqlite3').read_bytes()).hexdigest()
        path.write_text(json.dumps(data))

    def test_round_trip_exact_readonly_inspection_and_safe_summary(self):
        summary = self.bundle()
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.backup.iterdir()}
        self.assertEqual(inspect_backup(self.backup), summary)
        self.assertEqual(restore_backup(self.backup, self.target), summary)
        self.assertEqual(EvidenceStore(self.target).get(self.report['run_id']), self.detail)
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.backup.iterdir()})
        self.assertEqual(set(before), {'manifest.json', 'evidence.sqlite3'})
        self.assertEqual(summary['ledger_count'], 2)
        self.assertEqual(summary['run_count'], 1)
        self.assertNotIn('synthetic private note', str(summary))
        self.assertFalse(summary['encrypted'])
        self.assertFalse(summary['authenticated'])
        if os.name == 'posix':
            for folder in (self.backup, self.target):
                self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
                for path in folder.iterdir(): self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_missing_source_never_created(self):
        missing = self.root / 'missing'
        with self.assertRaises(RecoveryError): create_backup(missing, self.backup)
        self.assertFalse(missing.exists())
        self.assertFalse(self.backup.exists())

    def test_existing_destinations_preserved(self):
        self.bundle()
        for function, source, target in ((create_backup, self.workspace, self.workspace),
                                         (create_backup, self.workspace, self.backup),
                                         (restore_backup, self.backup, self.backup),
                                         (restore_backup, self.backup, self.workspace)):
            with self.subTest(function=function), self.assertRaises(RecoveryError): function(source, target)
        self.assertEqual(self.store.get(self.report['run_id']), self.detail)
        inspect_backup(self.backup)

    def test_missing_extra_files_and_checksum_fail(self):
        self.bundle()
        extra = self.backup / 'extra'; extra.write_text('unknown')
        with self.assertRaises(RecoveryError): inspect_backup(self.backup)
        extra.unlink()
        db = self.backup / 'evidence.sqlite3'; original = db.read_bytes()
        db.write_bytes(original + b'tampered')
        with self.assertRaises(RecoveryError): restore_backup(self.backup, self.target)
        self.assertFalse(self.target.exists())
        db.write_bytes(original)
        (self.backup / 'manifest.json').unlink()
        with self.assertRaises(RecoveryError): inspect_backup(self.backup)

    def test_unknown_manifest_version_and_fields(self):
        self.bundle()
        path = self.backup / 'manifest.json'; original = json.loads(path.read_text())
        for changes in ({'format_version': 99}, {'format_version': True}, {'surprise': 'x'}, {'authenticated': True}):
            path.write_text(json.dumps({**original, **changes}))
            with self.assertRaises(RecoveryError): inspect_backup(self.backup)

    def test_recomputed_checksum_does_not_hide_schema_or_chain_changes(self):
        self.bundle()
        db = self.backup / 'evidence.sqlite3'; original = db.read_bytes()
        for sql in ('CREATE TABLE hidden (data TEXT)',
                    'CREATE VIEW hidden AS SELECT * FROM ledger',
                    'CREATE TRIGGER hidden AFTER INSERT ON ledger BEGIN DELETE FROM metadata; END',
                    "UPDATE ledger SET payload='{}' WHERE seq=1",
                    'ALTER TABLE ledger ADD COLUMN hidden TEXT'):
            db.write_bytes(original)
            with closing(sqlite3.connect(db)) as connection, connection: connection.execute(sql)
            self.update_checksum()
            with self.subTest(sql=sql), self.assertRaises(RecoveryError): inspect_backup(self.backup)

    def test_hardlinks_rejected(self):
        self.bundle()
        db = self.backup / 'evidence.sqlite3'; linked = self.root / 'linked'
        os.link(db, linked)
        with self.assertRaises(RecoveryError): inspect_backup(self.backup)
        linked.unlink()

    def test_symlinks_rejected(self):
        self.bundle()
        linked = self.root / 'linked'
        try: linked.symlink_to(self.backup, target_is_directory=True)
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 1314: self.skipTest('Windows symlink privilege unavailable')
            raise
        with self.assertRaises(RecoveryError): inspect_backup(linked)

    @unittest.skipUnless(os.name == 'posix', 'POSIX permissions')
    def test_permissive_bundle_rejected_without_fixing_permissions(self):
        self.bundle(); os.chmod(self.backup, 0o755)
        with self.assertRaises(RecoveryError): inspect_backup(self.backup)
        self.assertEqual(self.backup.stat().st_mode & 0o777, 0o755)

    def test_active_writer_snapshot_is_consistent(self):
        def writes():
            for _ in range(6): self.store.save(report())
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            future = pool.submit(writes)
            summary = self.bundle()
            future.result()
        self.assertGreaterEqual(summary['run_count'], 1)
        self.assertLessEqual(summary['run_count'], 7)
        restore_backup(self.backup, self.target)
        self.assertEqual(len(EvidenceStore(self.target).list_runs()), summary['run_count'])

    def test_failed_completion_leaves_no_valid_bundle(self):
        with patch('rehearsal.recovery._write_manifest', side_effect=OSError('disk full')):
            with self.assertRaises(RecoveryError): self.bundle()
        with self.assertRaises(RecoveryError): inspect_backup(self.backup)
        self.assertEqual(self.store.get(self.report['run_id']), self.detail)

    def test_wal_writer_snapshot_preserves_committed_evidence(self):
        with closing(sqlite3.connect(self.store.path)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            self.store.save(report())
            # Keep WAL active while the backup reads a committed snapshot.
            summary = self.bundle()
        self.assertEqual(summary['run_count'], 2)
        self.assertEqual(inspect_backup(self.backup), summary)
        restore_backup(self.backup, self.target)
        self.assertEqual(EvidenceStore(self.target).get(self.report['run_id']), self.detail)

    def test_empty_target_and_unfinished_restore_preserved(self):
        self.bundle(); self.target.mkdir(mode=0o700)
        with self.assertRaises(RecoveryError): restore_backup(self.backup, self.target)
        self.assertEqual(list(self.target.iterdir()), [])
        self.target.rmdir()
        from rehearsal import recovery
        original = recovery._checksum
        def broken(path):
            if path.parent == self.target: raise OSError('resource failure')
            return original(path)
        with patch('rehearsal.recovery._checksum', side_effect=broken):
            with self.assertRaises(RecoveryError): restore_backup(self.backup, self.target)
        self.assertTrue((self.target / '.recovery-incomplete').is_file())
        from rehearsal.storage import StorageError
        with self.assertRaises(StorageError): EvidenceStore(self.target)
        inspect_backup(self.backup)

    def test_snapshot_failure_closes_both_connections(self):
        from unittest.mock import MagicMock
        from rehearsal import recovery
        real_connect = sqlite3.connect
        connections = []
        def connect(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            connections.append(connection)
            if len(connections) == 1:
                wrapped = MagicMock(wraps=connection)
                wrapped.backup.side_effect = sqlite3.OperationalError('disk full')
                return wrapped
            return connection
        with patch.object(recovery.sqlite3, 'connect', side_effect=connect):
            with self.assertRaises(RecoveryError): self.bundle()
        self.assertEqual(len(connections), 2)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError): connection.execute('SELECT 1')
        with self.assertRaises(RecoveryError): inspect_backup(self.backup)

    def test_bundle_sidecars_and_duplicate_json_rejected(self):
        self.bundle()
        sidecar = self.backup / 'evidence.sqlite3-wal'
        sidecar.touch(mode=0o600)
        with self.assertRaises(RecoveryError): inspect_backup(self.backup)
        sidecar.unlink()
        manifest = self.backup / 'manifest.json'
        raw = manifest.read_text()
        manifest.write_text(raw.replace('{', '{"format_version":1,', 1))
        with self.assertRaises(RecoveryError): inspect_backup(self.backup)

    def test_size_caps_reject_before_payload_loading(self):
        self.bundle()
        with patch('rehearsal.recovery.MAX_DATABASE_BYTES', 10):
            with self.assertRaises(RecoveryError): inspect_backup(self.backup)
        with patch('rehearsal.storage.MAX_PAYLOAD_BYTES', 10):
            with self.assertRaises(RecoveryError): inspect_backup(self.backup)
        with patch('rehearsal.storage.MAX_LEDGER_ROWS', 1):
            with self.assertRaises(RecoveryError): inspect_backup(self.backup)
        with patch('rehearsal.recovery.MANIFEST_LIMIT', 10):
            with self.assertRaises(RecoveryError): inspect_backup(self.backup)

    def test_python310_connection_without_setlimit(self):
        real_connect = sqlite3.connect
        class LegacyConnection:
            def __init__(self, connection): self.connection = connection
            def __getattr__(self, name):
                if name == 'setlimit': raise AttributeError(name)
                return getattr(self.connection, name)
        self.bundle()
        with patch('rehearsal.recovery.sqlite3.connect', side_effect=lambda *a, **k: LegacyConnection(real_connect(*a, **k))):
            self.assertEqual(inspect_backup(self.backup)['run_count'], 1)

    def test_empty_store_round_trip(self):
        empty = self.root / 'empty'
        EvidenceStore(empty)
        summary = create_backup(empty, self.backup)
        self.assertEqual(summary['ledger_count'], 0)
        self.assertEqual(summary['run_count'], 0)
        restore_backup(self.backup, self.target)
        self.assertEqual(EvidenceStore(self.target).list_runs(), [])

    def test_unknown_payload_with_recomputed_hashes_rejected(self):
        self.bundle()
        from rehearsal.storage import canonical, sha, ZERO
        db = self.backup / 'evidence.sqlite3'
        with closing(sqlite3.connect(db)) as connection, connection:
            payload = {'type': 'execute', 'url': 'https://example.invalid'}
            digest = sha({'previous': ZERO, 'payload': payload})
            connection.execute('DELETE FROM ledger')
            connection.execute('INSERT INTO ledger VALUES (1,?,?,?)', (canonical(payload), ZERO, digest))
            connection.execute('UPDATE metadata SET head=?,count=1', (digest,))
        self.update_checksum()
        with self.assertRaises(RecoveryError): restore_backup(self.backup, self.target)
        self.assertFalse(self.target.exists())

    def test_backup_and_failed_backup_cannot_be_used_as_workspaces(self):
        from rehearsal.storage import StorageError
        self.bundle()
        with self.assertRaises(StorageError): EvidenceStore(self.backup)
        failed = self.root / 'failed'
        with patch('rehearsal.recovery._write_manifest', side_effect=OSError('disk full')):
            with self.assertRaises(RecoveryError): create_backup(self.workspace, failed)
        self.assertTrue((failed / '.recovery-incomplete').is_file())
        with self.assertRaises(StorageError): EvidenceStore(failed)
