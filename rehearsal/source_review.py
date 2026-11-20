"""Immutable local review statements. Unkeyed hashes are not authentication."""
import datetime as dt
import json
import os
import re

from .source_evidence import inspect_local_sources, _local_path, _read_local_markdown
from .storage import canonical, sha
from .validation import _unique_pairs, _reject_constant

MAX_RECORD_BYTES = 32768
STATUSES = {'REVIEWED', 'CHANGES_REQUESTED'}
HASH_KEYS = {'before_raw_sha256', 'after_raw_sha256', 'before_content_sha256',
             'after_content_sha256', 'comparison_sha256'}
FIELDS = HASH_KEYS | {'created_at', 'reviewer', 'review_status', 'note',
                      'authenticated', 'deployment_approval', 'provenance'}


def _metadata(reviewer, status, note):
    if (type(reviewer) is not str or not reviewer.strip() or len(reviewer) > 100
            or type(status) is not str or status not in STATUSES
            or type(note) is not str or len(note) > 1000):
        raise ValueError('Invalid review metadata')


def _binding(evidence):
    return {'before_raw_sha256': evidence['before']['raw_sha256'],
            'after_raw_sha256': evidence['after']['raw_sha256'],
            'before_content_sha256': evidence['before']['content_sha256'],
            'after_content_sha256': evidence['after']['content_sha256'],
            'comparison_sha256': sha(evidence)}


def _validate(envelope):
    if (type(envelope) is not dict or set(envelope) != {'format_version', 'record', 'record_sha256'}
            or type(envelope['format_version']) is not int or envelope['format_version'] != 1):
        raise ValueError('Unsupported review record')
    record = envelope['record']
    if (type(record) is not dict or set(record) != FIELDS
            or record['authenticated'] is not False or record['deployment_approval'] is not False
            or record['provenance'] != 'unverified_local_files'
            or type(record['created_at']) is not str or len(record['created_at']) > 64):
        raise ValueError('Invalid review record')
    _metadata(record['reviewer'], record['review_status'], record['note'])
    if dt.datetime.fromisoformat(record['created_at']).tzinfo is None:
        raise ValueError('Invalid review timestamp')
    for key in HASH_KEYS:
        if type(record[key]) is not str or re.fullmatch('[0-9a-f]{64}', record[key]) is None:
            raise ValueError('Invalid source binding')
    if envelope['record_sha256'] != sha(record):
        raise ValueError('Review checksum mismatch')
    return record


def record_review(before, after, destination, *, reviewer, status, note=''):
    """Save an explicit operator statement in a new file; never approve deployment."""
    _metadata(reviewer, status, note)
    evidence = inspect_local_sources(before, after)
    record = {'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'reviewer': reviewer, 'review_status': status, 'note': note,
              'authenticated': False, 'deployment_approval': False,
              'provenance': 'unverified_local_files', **_binding(evidence)}
    envelope = {'format_version': 1, 'record': record, 'record_sha256': sha(record)}
    _validate(envelope)
    raw = (canonical(envelope) + '\n').encode('utf-8')
    if len(raw) > MAX_RECORD_BYTES:
        raise ValueError('Review record too large')
    path = _local_path(destination, allowed_suffixes=('.json',))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        # Failed partial writes remain for inspection; never overwrite/delete.
        raise ValueError('Review record could not be saved') from None
    return {'record_sha256': envelope['record_sha256'], 'review_status': status,
            'authenticated': False, 'deployment_approval': False, 'recorded': True}


def verify_review(source, before, after):
    """CURRENT is a source binding, not a recommendation or authenticated decision."""
    _, raw, _ = _read_local_markdown(source, allowed_suffixes=('.json',), maximum=MAX_RECORD_BYTES)
    envelope = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    record = _validate(envelope)
    current = _binding(inspect_local_sources(before, after))
    changed = sorted(key for key in HASH_KEYS if record[key] != current[key])
    return {'binding': 'STALE' if changed else 'CURRENT', 'changed_bindings': changed,
            'review_status': record['review_status'], 'record_sha256': envelope['record_sha256'],
            'authenticated': False, 'deployment_approval': False}
