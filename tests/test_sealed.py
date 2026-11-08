"""Synthetic passphrases only; exercise the production full-cost KDF."""
import hashlib
import importlib.util
import json
import sqlite3
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rehearsal.storage import EvidenceStore
from rehearsal.recovery import create_backup
from rehearsal import sealed
from tests.test_storage import report

PHRASE = b'synthetic test phrase only'


@unittest.skipUnless(importlib.util.find_spec('cryptography'),
                     'Optional sealed tests require cryptography')
class SealedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'work'
        self.bundle = self.root / 'bundle'
        self.file = self.root / 'sealed.ax'
        self.target = self.root / 'restored'
        store = EvidenceStore(self.workspace)
        self.report = report()
        saved = store.save(self.report)
        self.detail = store.review(self.report['run_id'], {
            'expected_revision': 0, 'report_sha256': saved['sha256'],
            'status': 'CHANGES_REQUESTED', 'note': 'synthetic secret marker 8273'})
        create_backup(self.workspace, self.bundle)

    def seal(self):
        return sealed.seal_backup(self.bundle, self.file, PHRASE)

    def test_roundtrip_and_randomness(self):
        before = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        summary = self.seal()
        other = self.root / 'other.ax'
        sealed.seal_backup(self.bundle, other, PHRASE)
        a, b = self.file.read_bytes(), other.read_bytes()
        self.assertNotEqual(a, b)
        self.assertNotEqual(a[9:25], b[9:25])
        self.assertNotEqual(a[25:37], b[25:37])
        self.assertNotIn(b'synthetic secret marker 8273', a)
        inspected = sealed.inspect_sealed(self.file, PHRASE)
        restored = sealed.restore_sealed(self.file, self.target, PHRASE)
        self.assertEqual(summary['verification'], 'SOURCE_DATABASE_VERIFIED')
        self.assertTrue(summary['database_verified'])
        self.assertEqual(inspected['verification'], 'AUTHENTICATED_ENVELOPE')
        self.assertFalse(inspected['database_verified'])
        self.assertEqual(restored['verification'], 'RESTORED_DATABASE_VERIFIED')
        self.assertTrue(restored['database_verified'])
        for output in (inspected, restored):
            for key in summary.keys() - {'verification', 'database_verified'}:
                self.assertEqual(summary[key], output[key])
        self.assertEqual(EvidenceStore(self.target).get(self.report['run_id']), self.detail)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.bundle.iterdir()})
        self.assertTrue(summary['encrypted'])
        self.assertTrue(summary['integrity_protected'])
        self.assertFalse(summary['signer_authenticated'])
        self.assertNotIn('note', str(summary))
        if os.name == 'posix':
            self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.target.stat().st_mode & 0o777, 0o700)
            self.assertEqual((self.target / 'evidence.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_wrong_phrase_and_corruption_never_create_plaintext(self):
        self.seal()
        original = self.file.read_bytes()
        cases = [original[:-1], original + b'x']
        for offset in (9, 25, sealed.HEADER.size, len(original) - 1):
            changed = bytearray(original); changed[offset] ^= 1; cases.append(bytes(changed))
        with self.assertRaisesRegex(sealed.SealedError, 'Sealed backup validation failed'):
            sealed.restore_sealed(self.file, self.target, b'wrong synthetic test phrase')
        self.assertFalse(self.target.exists())
        for data in cases:
            self.file.write_bytes(data)
            with self.assertRaises(sealed.SealedError): sealed.restore_sealed(self.file, self.target, PHRASE)
            self.assertFalse(self.target.exists())

    def test_bad_headers_rejected_before_kdf(self):
        self.seal(); original = self.file.read_bytes()
        cases = [b'', b'wrong header', original[:8] + b'\xff' + original[9:]]
        fields = list(sealed.HEADER.unpack(original[:sealed.HEADER.size]))
        fields[-1] = sealed.MAX_CIPHERTEXT + 1
        cases.append(sealed.HEADER.pack(*fields) + original[sealed.HEADER.size:])
        for data in cases:
            self.file.write_bytes(data)
            with patch.object(sealed, '_derive_key', side_effect=AssertionError('KDF reached')) as derive:
                with self.assertRaises(sealed.SealedError): sealed.inspect_sealed(self.file, PHRASE)
                derive.assert_not_called()

    def test_existing_destinations_and_paths(self):
        self.seal(); original = self.file.read_bytes()
        with self.assertRaises(sealed.SealedError): self.seal()
        self.assertEqual(self.file.read_bytes(), original)
        self.target.mkdir(mode=0o700)
        with self.assertRaises(sealed.SealedError): sealed.restore_sealed(self.file, self.target, PHRASE)
        self.assertEqual(list(self.target.iterdir()), [])
        for path in (self.bundle / 'inside.ax', self.bundle, '//network/share', '\\\\network\\share'):
            with self.assertRaises(sealed.SealedError): sealed.seal_backup(self.bundle, path, PHRASE)

    def test_sealed_symlink_rejected(self):
        self.seal()
        link = self.root / 'link.ax'
        try:
            link.symlink_to(self.file)
        except OSError as exc:
            if getattr(exc, 'winerror', None) == 1314:
                self.skipTest('Windows symlink privilege unavailable')
            raise
        with self.assertRaises(sealed.SealedError): sealed.inspect_sealed(link, PHRASE)

    def test_sealed_hardlink_rejected(self):
        self.seal()
        hardlink = self.root / 'hard.ax'; os.link(self.file, hardlink)
        with self.assertRaises(sealed.SealedError): sealed.inspect_sealed(self.file, PHRASE)

    def test_unsafe_permissions_and_phrase_limits(self):
        for phrase in (b'', b'short', b'x' * 1025, b'\xff' * 12, '합성문구'.encode(), 'not bytes phrase'):
            with self.assertRaises(sealed.SealedError): sealed.seal_backup(self.bundle, self.file, phrase)
            self.assertFalse(self.file.exists())
        if os.name == 'posix':
            self.seal(); self.file.chmod(0o644)
            with self.assertRaises(sealed.SealedError): sealed.inspect_sealed(self.file, PHRASE)

    def test_changed_source_after_inspection(self):
        inspect = sealed.recovery._inspect
        def change(source):
            result = inspect(source)
            with (self.bundle / 'evidence.sqlite3').open('ab') as stream: stream.write(b'changed')
            return result
        with patch.object(sealed.recovery, '_inspect', side_effect=change):
            with self.assertRaises(sealed.SealedError): self.seal()
        self.assertFalse(self.file.exists())

    def test_authenticated_invalid_payloads(self):
        self.seal()
        raw = self.file.read_bytes(); header = raw[:sealed.HEADER.size]
        _, _, salt, nonce, _ = sealed.HEADER.unpack(header)
        AESGCM, _ = sealed._crypto()
        cipher = AESGCM(sealed._derive_key(PHRASE, salt))
        payload = cipher.decrypt(nonce, raw[sealed.HEADER.size:], header)
        cases = [b'\xff\xff\xff\xff' + payload[4:], payload[:-1], payload + b'bad']
        for data in cases:
            fields = list(sealed.HEADER.unpack(header)); fields[-1] = len(data) + 16
            new_header = sealed.HEADER.pack(*fields)
            self.file.write_bytes(new_header + cipher.encrypt(nonce, data, new_header))
            with self.assertRaises(sealed.SealedError): sealed.restore_sealed(self.file, self.target, PHRASE)
            self.assertFalse(self.target.exists())

    def test_restore_failure_retains_incomplete_marker(self):
        self.seal()
        with patch.object(sealed.recovery, '_validated_database', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(sealed.SealedError): sealed.restore_sealed(self.file, self.target, PHRASE)
        self.assertTrue((self.target / '.recovery-incomplete').exists())
        with self.assertRaises(Exception): EvidenceStore(self.target)

    def test_publication_failure_never_publishes_partial_file(self):
        with patch.object(sealed.os, 'link', side_effect=OSError('synthetic failure')):
            with self.assertRaises(sealed.SealedError): self.seal()
        self.assertFalse(self.file.exists())
        self.assertFalse(list(self.root.glob('.sealed-*')))

    def test_missing_crypto_is_explicit(self):
        with patch.dict('sys.modules', {'cryptography.hazmat.primitives.ciphers.aead': None}):
            with self.assertRaisesRegex(sealed.SealedError, 'dependency is unavailable'):
                self.seal()
        self.assertFalse(self.file.exists())

    def test_forged_authenticated_schema_and_manifest(self):
        self.seal()
        raw = self.file.read_bytes()
        fields = list(sealed.HEADER.unpack(raw[:sealed.HEADER.size]))
        cipher = sealed._crypto()[0](sealed._derive_key(PHRASE, fields[2]))
        dbpath = self.bundle / 'evidence.sqlite3'
        connection = sqlite3.connect(dbpath)
        try:
            connection.execute('CREATE TABLE unexpected (data TEXT)')
            connection.commit()
        finally:
            connection.close()
        database = dbpath.read_bytes()
        manifest = json.loads((self.bundle / 'manifest.json').read_bytes())
        manifest['database_sha256'] = hashlib.sha256(database).hexdigest()
        manifest_raw = sealed.canonical(manifest).encode()
        for index, manifest_bytes in enumerate((manifest_raw, json.dumps(manifest, indent=2).encode())):
            payload = sealed.MANIFEST_LENGTH.pack(len(manifest_bytes)) + manifest_bytes + database
            fields[-1] = len(payload) + 16
            header = sealed.HEADER.pack(*fields)
            self.file.write_bytes(header + cipher.encrypt(fields[3], payload, header))
            target = self.root / ('invalid-target-' + str(index))
            if index == 0:
                inspected = sealed.inspect_sealed(self.file, PHRASE)
                self.assertFalse(inspected['database_verified'])
                self.assertEqual(inspected['verification'], 'AUTHENTICATED_ENVELOPE')
            else:
                with self.assertRaises(sealed.SealedError): sealed.inspect_sealed(self.file, PHRASE)
            with self.assertRaises(sealed.SealedError): sealed.restore_sealed(self.file, target, PHRASE)
            if index == 0:
                self.assertTrue((target / '.recovery-incomplete').exists())
                self.assertEqual((target / 'evidence.sqlite3').read_bytes(), database)
                with self.assertRaises(Exception): EvidenceStore(target)
            else:
                self.assertFalse(target.exists())

    def test_inspect_does_not_open_database_or_write_files(self):
        self.seal()
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                  for path in self.root.rglob('*') if path.is_file()}
        with patch.object(sqlite3, 'connect', side_effect=AssertionError('SQLite parsing forbidden')):
            result = sealed.inspect_sealed(self.file, PHRASE)
        self.assertEqual(result['verification'], 'AUTHENTICATED_ENVELOPE')
        self.assertFalse(result['database_verified'])
        after = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                 for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(before, after)

    def test_authenticated_invalid_database_or_ledger_claim_retains_marker(self):
        self.seal()
        raw = self.file.read_bytes()
        fields = list(sealed.HEADER.unpack(raw[:sealed.HEADER.size]))
        cipher = sealed._crypto()[0](sealed._derive_key(PHRASE, fields[2]))
        original_manifest = json.loads((self.bundle / 'manifest.json').read_bytes())
        original_database = (self.bundle / 'evidence.sqlite3').read_bytes()
        cases = [(b'not SQLite at all', {}),
                 (original_database, {'run_count': 0}),
                 (original_database, {'ledger_head': '0' * 64}),
                 (original_database, {'ledger_count': 0})]
        for index, (database, changes) in enumerate(cases):
            manifest = {**original_manifest, **changes,
                        'database_sha256': hashlib.sha256(database).hexdigest()}
            manifest_raw = sealed.canonical(manifest).encode()
            payload = sealed.MANIFEST_LENGTH.pack(len(manifest_raw)) + manifest_raw + database
            fields[-1] = len(payload) + 16
            header = sealed.HEADER.pack(*fields)
            self.file.write_bytes(header + cipher.encrypt(fields[3], payload, header))
            self.assertFalse(sealed.inspect_sealed(self.file, PHRASE)['database_verified'])
            target = self.root / ('invalid-database-' + str(index))
            with self.assertRaises(sealed.SealedError): sealed.restore_sealed(self.file, target, PHRASE)
            self.assertTrue((target / '.recovery-incomplete').exists())
            self.assertEqual((target / 'evidence.sqlite3').read_bytes(), database)
            with self.assertRaises(Exception): EvidenceStore(target)

    def test_sparse_oversized_input_rejected_before_kdf(self):
        self.file.touch(mode=0o600)
        with self.file.open('wb') as stream: stream.truncate(sealed.MAX_SEALED_BYTES + 1)
        with patch.object(sealed, '_derive_key') as derive:
            with self.assertRaises(sealed.SealedError): sealed.inspect_sealed(self.file, PHRASE)
            derive.assert_not_called()

    def test_sync_failure_does_not_publish_ciphertext(self):
        with patch.object(sealed.os, 'fsync', side_effect=OSError('synthetic write failure')):
            with self.assertRaises(sealed.SealedError): self.seal()
        self.assertFalse(self.file.exists())
        self.assertFalse(list(self.root.glob('.sealed-*')))

    def test_restore_closes_connection_on_validation_failure(self):
        self.seal()
        original_connect = sqlite3.connect
        closed = []
        class TrackedConnection(sqlite3.Connection):
            def close(self):
                closed.append(True)
                super().close()
        def connect(*args, **kwargs):
            return original_connect(*args, **kwargs, factory=TrackedConnection)
        with patch.object(sealed.recovery.sqlite3, 'connect', side_effect=connect), patch.object(sealed.recovery, 'check_schema', side_effect=ValueError('synthetic failure')):
            with self.assertRaises(sealed.SealedError): sealed.restore_sealed(self.file, self.target, PHRASE)
        self.assertEqual(closed, [True])

    def test_short_writes_rejected(self):
        from unittest.mock import Mock
        with self.assertRaises(sealed.SealedError):
            sealed._write_exact(Mock(write=Mock(return_value=1)), b'full data')

    def test_partial_plaintext_write_retains_marker(self):
        self.seal()
        original_create = sealed.recovery._create_file
        class PartialWrite:
            def __init__(self, path): self.stream = original_create(path)
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def write(self, data):
                self.stream.write(data[:16])
                raise OSError('synthetic partial write')
        def create(path):
            return PartialWrite(path) if path.name == 'evidence.sqlite3' else original_create(path)
        with patch.object(sealed.recovery, '_create_file', side_effect=create):
            with self.assertRaises(sealed.SealedError): sealed.restore_sealed(self.file, self.target, PHRASE)
        self.assertTrue((self.target / '.recovery-incomplete').exists())
        self.assertEqual((self.target / 'evidence.sqlite3').stat().st_size, 16)
        with self.assertRaises(Exception): EvidenceStore(self.target)

    def test_wal_origin_roundtrip_preserves_original_bytes(self):
        connection = sqlite3.connect(self.workspace / 'evidence.sqlite3')
        try: self.assertEqual(connection.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
        finally: connection.close()
        bundle = self.root / 'walbundle'
        create_backup(self.workspace, bundle)
        original = (bundle / 'evidence.sqlite3').read_bytes()
        self.assertEqual(original[18:20], bytes([2, 2]))
        sealed.seal_backup(bundle, self.file, PHRASE)
        sealed.inspect_sealed(self.file, PHRASE)
        sealed.restore_sealed(self.file, self.target, PHRASE)
        self.assertEqual((self.target / 'evidence.sqlite3').read_bytes(), original)
        self.assertEqual((bundle / 'evidence.sqlite3').read_bytes(), original)
        self.assertEqual(EvidenceStore(self.target).get(self.report['run_id']), self.detail)


class SealedCapabilityTests(unittest.TestCase):
    def test_support_does_not_require_sqlite_deserialize(self):
        with patch.object(sealed, '_crypto'), patch.object(sqlite3, 'Connection', object):
            self.assertIsNone(sealed.check_support())

    def test_no_crypto_fails_explicitly(self):
        with patch.dict('sys.modules', {'cryptography.hazmat.primitives.ciphers.aead': None}):
            with self.assertRaisesRegex(sealed.SealedDependencyError, 'dependency is unavailable'):
                sealed.check_support()
