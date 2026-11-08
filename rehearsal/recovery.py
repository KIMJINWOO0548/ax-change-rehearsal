"""Bounded local recovery, not encryption, authentication, or an archive importer.

Format 1 holds exactly a SQLite database (<=128 MiB) and JSON manifest (<=4 KiB).
The unkeyed checksums detect accidental damage, not rewriting by a local owner.
Incomplete destinations are retained for operator inspection, never overwritten.
"""
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time

from .storage import (EvidenceStore, StorageError, MAX_DATABASE_BYTES,
                      MAX_LEDGER_ROWS, LIMIT, canonical, check_schema)
from .validation import _reject_constant, _unique_pairs

FORMAT_VERSION = 1
MANIFEST_LIMIT = 4096
DATABASE = 'evidence.sqlite3'
MANIFEST = 'manifest.json'
INCOMPLETE = '.recovery-incomplete'
FIELDS = {'format_version', 'database_sha256', 'ledger_head', 'ledger_count',
          'run_count', 'created_at', 'encrypted', 'authenticated'}


class RecoveryError(StorageError):
    """A recovery operation failed closed; messages exclude user data and paths."""


def _path(value):
    raw = os.fspath(value)
    if not isinstance(raw, str) or '\x00' in raw or '://' in raw or '..' in Path(raw).parts:
        raise RecoveryError('Invalid local path')
    path = Path(os.path.abspath(raw))
    for part in (path, *path.parents):
        if part.is_symlink(): raise RecoveryError('Unsafe recovery path')
    return path


def _private(path, directory=False, maximum=None, allow_empty=False):
    info = path.lstat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise RecoveryError('Unsafe recovery path')
    if os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise RecoveryError('Recovery paths must be private and owned by current user')
    if not directory and info.st_nlink != 1: raise RecoveryError('Unsafe recovery links')
    if maximum is not None and (info.st_size < (0 if allow_empty else 1) or info.st_size > maximum):
        raise RecoveryError('Invalid recovery file size')


def _source(value, bundle=False):
    path = _path(value)
    _private(path, directory=True)
    if bundle and {p.name for p in path.iterdir()} != {DATABASE, MANIFEST}:
        raise RecoveryError('Incomplete or unsupported recovery bundle')
    if (path / INCOMPLETE).exists(): raise RecoveryError('Incomplete recovery destination')
    _private(path / DATABASE, maximum=MAX_DATABASE_BYTES)
    if bundle:
        _private(path / MANIFEST, maximum=MANIFEST_LIMIT)
    else:
        for suffix in ('-journal', '-wal', '-shm'):
            candidate = path / (DATABASE + suffix)
            if candidate.exists() or candidate.is_symlink():
                _private(candidate, maximum=MAX_DATABASE_BYTES, allow_empty=True)
    return path


def _new_destination(value, source):
    path = _path(value)
    if path == source or source in path.parents or path in source.parents:
        raise RecoveryError('Source and destination must be separate')
    # mkdir is exclusive, including when an empty directory already exists.
    path.mkdir(mode=0o700)
    _private(path, directory=True)
    return path


@contextmanager
def _read_connection(path, immutable=False):
    connection = None
    try:
        uri = path.as_uri() + '?mode=ro' + ('&immutable=1' if immutable else '')
        connection = sqlite3.connect(uri, uri=True, timeout=10)
        # Python 3.10 lacks setlimit. File/row/payload bounds still apply there.
        if hasattr(connection, 'setlimit'):
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2 * 1024 * 1024)
            connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 16384)
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        check_schema(connection)
        yield connection
    finally:
        if connection is not None: connection.close()


def _validated_database(path):
    # No EvidenceStore constructor: inspection must never create/repair files.
    with _read_connection(path, immutable=True) as connection:
        runs = EvidenceStore.__new__(EvidenceStore)._verify(connection)
        head, count = connection.execute('SELECT head,count FROM metadata WHERE id=1').fetchone()
    return runs, head, count


def _checksum(path):
    digest = hashlib.sha256()
    total = 0
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            total += len(block)
            if total > MAX_DATABASE_BYTES: raise RecoveryError('Recovery file too large')
            digest.update(block)
    return digest.hexdigest()


def _create_file(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    return os.fdopen(fd, 'wb')


def _sync_directory(path):
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(fd)
        finally: os.close(fd)


def _write_manifest(path, summary):
    with _create_file(path / MANIFEST) as stream:
        stream.write((canonical(summary) + '\n').encode('utf-8'))
        stream.flush(); os.fsync(stream.fileno())
    _sync_directory(path)


def _inspect(value):
    source = _source(value, bundle=True)
    raw = (source / MANIFEST).read_bytes()
    if len(raw) > MANIFEST_LIMIT: raise RecoveryError('Recovery manifest too large')
    manifest = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    if (type(manifest) is not dict or set(manifest) != FIELDS
            or type(manifest['format_version']) is not int or manifest['format_version'] != FORMAT_VERSION
            or manifest['encrypted'] is not False or manifest['authenticated'] is not False
            or type(manifest['ledger_count']) is not int or not 0 <= manifest['ledger_count'] <= MAX_LEDGER_ROWS
            or type(manifest['run_count']) is not int or not 0 <= manifest['run_count'] <= LIMIT
            or type(manifest['created_at']) is not str or len(manifest['created_at']) > 64):
        raise RecoveryError('Unsupported recovery manifest')
    if dt.datetime.fromisoformat(manifest['created_at']).tzinfo is None:
        raise RecoveryError('Invalid recovery timestamp')
    for key in ('database_sha256', 'ledger_head'):
        value = manifest[key]
        if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise RecoveryError('Invalid recovery digest')
    if _checksum(source / DATABASE) != manifest['database_sha256']:
        raise RecoveryError('Recovery checksum mismatch')
    runs, head, count = _validated_database(source / DATABASE)
    if (head, count, len(runs)) != (manifest['ledger_head'], manifest['ledger_count'], manifest['run_count']):
        raise RecoveryError('Recovery ledger mismatch')
    return source, manifest, runs


def inspect_backup(source):
    """Verify a closed two-file bundle without opening it for writes."""
    try: return _inspect(source)[1]
    except RecoveryError: raise
    except Exception as exc: raise RecoveryError('Recovery inspection failed') from exc


def create_backup(workspace, destination):
    """Create an exclusive destination using SQLite's consistent online backup."""
    try:
        source = _source(workspace)
        with _read_connection(source / DATABASE) as original:
            target = _new_destination(destination, source)
            with _create_file(target / INCOMPLETE) as marker:
                marker.write(b'Incomplete backup; do not use as workspace.\n')
                marker.flush(); os.fsync(marker.fileno())
            with _create_file(target / DATABASE): pass
            copied = None
            try:
                copied = sqlite3.connect(str(target / DATABASE), timeout=10)
                copied.execute('PRAGMA trusted_schema=OFF')
                deadline = time.monotonic() + 30
                page_size = original.execute('PRAGMA page_size').fetchone()[0]
                def progress(status, remaining, total):
                    if total * page_size > MAX_DATABASE_BYTES or time.monotonic() > deadline:
                        raise RecoveryError('Recovery snapshot resource limit')
                original.backup(copied, pages=128, progress=progress, sleep=0.01)
            finally:
                if copied is not None: copied.close()
        _private(target / DATABASE, maximum=MAX_DATABASE_BYTES)
        with (target / DATABASE).open('r+b') as stream: os.fsync(stream.fileno())
        runs, head, count = _validated_database(target / DATABASE)
        summary = {'format_version': FORMAT_VERSION, 'database_sha256': _checksum(target / DATABASE),
                   'ledger_head': head, 'ledger_count': count, 'run_count': len(runs),
                   'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                   'encrypted': False, 'authenticated': False}
        _write_manifest(target, summary)
        (target / INCOMPLETE).unlink()
        _sync_directory(target)
        if inspect_backup(target) != summary: raise RecoveryError('Recovery verification failed')
        return summary
    except RecoveryError: raise
    except Exception as exc: raise RecoveryError('Backup creation failed') from exc


def restore_backup(source, destination):
    """Restore only validated local bundles; preserve the backup and existing paths."""
    try:
        source, summary, expected_runs = _inspect(source)
        target = _new_destination(destination, source)
        with _create_file(target / INCOMPLETE) as marker:
            marker.write(b'Incomplete recovery; do not use as workspace.\n')
            marker.flush(); os.fsync(marker.fileno())
        with (source / DATABASE).open('rb') as original, _create_file(target / DATABASE) as restored:
            total = 0
            while block := original.read(1024 * 1024):
                total += len(block)
                if total > MAX_DATABASE_BYTES: raise RecoveryError('Recovery file too large')
                restored.write(block)
            restored.flush(); os.fsync(restored.fileno())
        if _checksum(target / DATABASE) != summary['database_sha256']:
            raise RecoveryError('Restored checksum mismatch')
        actual_runs, head, count = _validated_database(target / DATABASE)
        if actual_runs != expected_runs or (head, count) != (summary['ledger_head'], summary['ledger_count']):
            raise RecoveryError('Restored evidence mismatch')
        (target / INCOMPLETE).unlink()
        _sync_directory(target)
        return summary
    except RecoveryError: raise
    except Exception as exc: raise RecoveryError('Restore failed') from exc
