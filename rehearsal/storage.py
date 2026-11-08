"""Local synthetic evidence only. Unkeyed hashes do not authenticate history.
A local owner can rewrite files and recompute hashes. No encryption or approval.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid
from .validation import _reject_constant, _unique_pairs

LIMIT = 100
ZERO = '0' * 64
class StorageError(Exception): pass
class StorageConflict(StorageError): pass
class StorageLimit(StorageError): pass
class RunNotFound(StorageError): pass

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
def sha(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()
def storage_info(enabled):
    return {'enabled': enabled, 'kind': 'local-synthetic', 'limit': LIMIT, 'review_is_approval': False}

class EvidenceStore:
    def __init__(self, workspace, limit=LIMIT):
        if type(limit) is not int or not 1 <= limit <= LIMIT:
            raise ValueError('Invalid storage limit')
        self.limit = limit
        self.workspace = Path(os.path.abspath(workspace))
        self.path = self.workspace / 'evidence.sqlite3'
        try:
            for part in [self.workspace, *self.workspace.parents]:
                if part.is_symlink(): raise StorageError('Unsafe workspace')
            if not self.workspace.exists(): self.workspace.mkdir(mode=0o700)
            self._check(self.workspace, True)
            if not self.path.exists():
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                os.close(fd)
                connection = self._connect()
                try:
                    connection.executescript('CREATE TABLE ledger (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL); CREATE TABLE metadata (id INTEGER PRIMARY KEY CHECK(id=1), head TEXT NOT NULL, count INTEGER NOT NULL);')
                    connection.execute('INSERT INTO metadata VALUES (1,?,0)', (ZERO,))
                    connection.commit()
                finally: connection.close()
            self._operate(lambda connection, runs: None)
        except StorageError: raise
        except Exception as exc: raise StorageError('Storage unavailable') from exc

    def _check(self, path, directory=False):
        info = path.lstat()
        if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            raise StorageError('Unsafe storage path')
        if os.name == 'posix' and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise StorageError('Storage must be private and owned by current user')
        if not directory and info.st_nlink != 1: raise StorageError('Unsafe storage links')

    def _connect(self):
        for part in [self.workspace, *self.workspace.parents]:
            if part.is_symlink(): raise StorageError('Unsafe workspace')
        self._check(self.workspace, True)
        self._check(self.path)
        for suffix in ('-journal', '-wal', '-shm'):
            candidate = Path(str(self.path) + suffix)
            if candidate.exists() or candidate.is_symlink(): self._check(candidate)
        connection = sqlite3.connect(str(self.path), timeout=10)
        try:
            connection.execute('PRAGMA synchronous=FULL')
            return connection
        except BaseException:
            connection.close()
            raise

    def _verify(self, connection):
        if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]: raise StorageError('Corrupt storage')
        rows = connection.execute('SELECT seq,payload,previous,hash FROM ledger ORDER BY seq').fetchall()
        runs, previous = {}, ZERO
        for index, (seq, raw, prev, digest) in enumerate(rows, 1):
            payload = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
            if seq != index or prev != previous or digest != sha({'previous': prev, 'payload': payload}):
                raise StorageError('Invalid evidence chain')
            previous = digest
            if payload['type'] == 'run':
                report = payload['report']; run_id = report['run_id']
                if run_id in runs or uuid.UUID(run_id).hex != run_id or report.get('synthetic_only') is not True:
                    raise StorageError('Invalid run')
                record = {'run_id': run_id, 'sha256': sha(report), 'created_at': report['created_at'],
                          'revision': 0, 'review_status': 'UNREVIEWED', 'review_is_approval': False}
                runs[run_id] = {'report': report, 'record': record, 'events': []}
            elif payload['type'] == 'review':
                entry = runs[payload['run_id']]; event = payload['event']
                self.validate_review({'expected_revision': event['revision'] - 1, 'report_sha256': event['report_sha256'], 'status': event['status'], 'note': event['note']})
                if event['revision'] != entry['record']['revision'] + 1 or event['report_sha256'] != entry['record']['sha256']:
                    raise StorageError('Invalid review binding')
                entry['record'].update(revision=event['revision'], review_status=event['status'])
                entry['events'].append({**event, 'event_sha256': digest, 'previous_sha256': prev})
            else: raise StorageError('Unknown evidence type')
        if connection.execute('SELECT id,head,count FROM metadata').fetchall() != [(1, previous, len(rows))]:
            raise StorageError('Invalid evidence head')
        if len(runs) > LIMIT: raise StorageError('Invalid evidence count')
        return runs

    def _operate(self, action):
        connection = None
        try:
            connection = self._connect(); connection.execute('BEGIN IMMEDIATE')
            runs = self._verify(connection)
            result = action(connection, runs)
            connection.commit()
            return result
        except StorageError: raise
        except Exception as exc: raise StorageError('Storage unavailable') from exc
        finally:
            if connection is not None: connection.close()

    def _append(self, connection, payload):
        head, count = connection.execute('SELECT head,count FROM metadata WHERE id=1').fetchone()
        digest = sha({'previous': head, 'payload': payload})
        connection.execute('INSERT INTO ledger VALUES (?,?,?,?)', (count + 1, canonical(payload), head, digest))
        connection.execute('UPDATE metadata SET head=?,count=? WHERE id=1', (digest, count + 1))

    def save(self, report):
        if report.get('synthetic_only') is not True or uuid.UUID(report['run_id']).hex != report['run_id']:
            raise ValueError('Only synthetic runs can be stored')
        def action(connection, runs):
            if len(runs) >= self.limit: raise StorageLimit('Storage full')
            if report['run_id'] in runs: raise StorageConflict('Duplicate run')
            self._append(connection, {'type': 'run', 'report': report})
            return self._verify(connection)[report['run_id']]['record']
        return self._operate(action)

    def list_runs(self):
        return self._operate(lambda connection, runs: [
            {**item['record'], **{key: item['report'][key] for key in ('configuration', 'scope', 'readiness', 'counts')}}
            for item in reversed(list(runs.values()))])

    def get(self, run_id):
        def action(connection, runs):
            if run_id not in runs: raise RunNotFound('Run not found')
            return runs[run_id]
        return self._operate(action)

    @staticmethod
    def validate_review(data):
        if (type(data) is not dict or set(data) != {'expected_revision', 'report_sha256', 'status', 'note'}
                or type(data['expected_revision']) is not int or data['expected_revision'] < 0
                or type(data['report_sha256']) is not str or len(data['report_sha256']) != 64
                or any(c not in '0123456789abcdef' for c in data['report_sha256'])
                or type(data['status']) is not str or data['status'] not in {'REVIEWED', 'CHANGES_REQUESTED'}
                or type(data['note']) is not str or len(data['note']) > 1000):
            raise ValueError('Invalid review')

    def review(self, run_id, data):
        self.validate_review(data)
        def action(connection, runs):
            if run_id not in runs: raise RunNotFound('Run not found')
            record = runs[run_id]['record']
            if record['revision'] != data['expected_revision'] or record['sha256'] != data['report_sha256']:
                raise StorageConflict('Review conflict')
            if record['revision'] >= 1000: raise StorageLimit('Review limit reached')
            event = {'revision': record['revision'] + 1, 'status': data['status'], 'note': data['note'],
                     'report_sha256': record['sha256'], 'created_at': dt.datetime.now(dt.timezone.utc).isoformat()}
            self._append(connection, {'type': 'review', 'run_id': run_id, 'event': event})
            return self._verify(connection)[run_id]
        return self._operate(action)
