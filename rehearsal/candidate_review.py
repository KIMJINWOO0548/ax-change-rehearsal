"""Source-bound operator dispositions, not authenticated or executable rules."""
from collections import Counter
import datetime as dt
import json
import os
import re
from .source_evidence import inspect_local_sources, _local_path, _read_local_markdown
from .change_candidates import build_change_candidates, MAX_CANDIDATES
from .source_review import _metadata
from .storage import canonical, sha
from .validation import _unique_pairs, _reject_constant

MAX_BYTES = 512 * 1024
DECISIONS = {'CONFIRMED_CHANGE', 'NOT_A_RULE', 'NEEDS_CLARIFICATION'}
FINAL = {'CONFIRMED_CHANGE', 'NOT_A_RULE'}


def read_json(path):
    _, raw, _ = _read_local_markdown(path, allowed_suffixes=('.json',), maximum=MAX_BYTES)
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def _hash(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def _validate_rows(rows, *, pending=False):
    if type(rows) is not list or len(rows) > MAX_CANDIDATES:
        raise ValueError('Invalid candidate decisions')
    seen = set()
    for row in rows:
        if (type(row) is not dict or set(row) != {'candidate_id', 'decision', 'reason'}
                or not _hash(row['candidate_id']) or row['candidate_id'] in seen
                or type(row['decision']) is not str
                or row['decision'] not in DECISIONS | ({'PENDING'} if pending else set())):
            raise ValueError('Invalid candidate decision')
        seen.add(row['candidate_id'])
        if row['decision'] == 'PENDING':
            if row['reason'] is not None:
                raise ValueError('Pending candidate has no reviewed reason')
        elif type(row['reason']) is not str or not row['reason'].strip() or len(row['reason']) > 1000:
            raise ValueError('Decision requires a bounded reason')
    return seen


def _current(before, after):
    evidence = inspect_local_sources(before, after)
    candidates = build_change_candidates(evidence)
    return sha(evidence), sha(candidates), [c['candidate_id'] for c in candidates['candidates']]


def _validate(envelope):
    if (type(envelope) is not dict or set(envelope) != {'format_version', 'record', 'record_sha256'}
            or type(envelope['format_version']) is not int or envelope['format_version'] != 1):
        raise ValueError('Unsupported candidate review')
    r = envelope['record']
    if (type(r) is not dict or set(r) != {'kind', 'created_at', 'reviewer', 'comparison_sha256',
                                        'candidates_sha256', 'candidates', 'authenticated', 'deployment_approval'}
            or r['kind'] != 'source_candidate_review'
            or r['authenticated'] is not False or r['deployment_approval'] is not False
            or not _hash(r['comparison_sha256']) or not _hash(r['candidates_sha256'])
            or type(r['created_at']) is not str or len(r['created_at']) > 64):
        raise ValueError('Invalid candidate review')
    _metadata(r['reviewer'], 'REVIEWED', '')
    if dt.datetime.fromisoformat(r['created_at']).tzinfo is None:
        raise ValueError('Invalid candidate review timestamp')
    _validate_rows(r['candidates'], pending=True)
    if not r['candidates'] or envelope['record_sha256'] != sha(r):
        raise ValueError('Candidate review checksum mismatch')
    return r


def _counts(rows):
    counts = Counter(row['decision'] for row in rows)
    return {state: counts[state] for state in sorted(DECISIONS | {'PENDING'})}


def record_candidate_review(before, after, destination, *, reviewer, decisions):
    _metadata(reviewer, 'REVIEWED', '')
    selected = _validate_rows(decisions)
    comparison_sha, candidates_sha, ids = _current(before, after)
    if not ids or not selected <= set(ids):
        raise ValueError('No candidates or stale candidate selection')
    by_id = {row['candidate_id']: row for row in decisions}
    rows = [dict(by_id[cid]) if cid in by_id else
            {'candidate_id': cid, 'decision': 'PENDING', 'reason': None} for cid in ids]
    record = {'kind': 'source_candidate_review', 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'reviewer': reviewer, 'comparison_sha256': comparison_sha, 'candidates_sha256': candidates_sha,
              'candidates': rows, 'authenticated': False, 'deployment_approval': False}
    envelope = {'format_version': 1, 'record': record, 'record_sha256': sha(record)}
    _validate(envelope)
    raw = (canonical(envelope) + '\n').encode('utf-8')
    if len(raw) > MAX_BYTES:
        raise ValueError('Candidate review too large')
    path = _local_path(destination, allowed_suffixes=('.json',))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        raise ValueError('Candidate review could not be saved') from None
    return {'recorded': True, 'record_sha256': envelope['record_sha256'], 'recorded_counts': _counts(rows),
            'authenticated': False, 'deployment_approval': False}


def verify_candidate_review(source, before, after):
    envelope = read_json(source)
    record = _validate(envelope)
    comparison_sha, candidates_sha, ids = _current(before, after)
    current = (comparison_sha == record['comparison_sha256'] and candidates_sha == record['candidates_sha256'])
    if current and ids != [row['candidate_id'] for row in record['candidates']]:
        raise ValueError('Candidate list does not match bound sources')
    unreviewed = (sum(row['decision'] not in FINAL for row in record['candidates']) if current else len(ids))
    return {'binding': 'CURRENT' if current else 'STALE', 'recorded_counts': _counts(record['candidates']),
            'current_candidate_count': len(ids), 'current_unreviewed_count': unreviewed,
            'review_complete': bool(ids) and current and unreviewed == 0,
            'record_sha256': envelope['record_sha256'], 'authenticated': False, 'deployment_approval': False}
