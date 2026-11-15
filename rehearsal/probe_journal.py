"""Durable intent/results for an opt-in disposable loopback diagnostic.

RECORDED describes persistence, not network success or business validation.
"""
import math
import re
from .network_probe import probe

STATUSES = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT', 'CLEANUP_FAILED'}

def validate_configuration(config):
    if (type(config) is not dict or set(config) != {'kind', 'port', 'timeout'}
            or config['kind'] != 'disposable-loopback-probe'
            or type(config['port']) is not int or not 1 <= config['port'] <= 65535
            or type(config['timeout']) not in (int, float) or not math.isfinite(config['timeout'])
            or not .05 <= config['timeout'] <= 30):
        raise ValueError('Invalid probe configuration')

def validate_outcome(value, attempt_id):
    required = {'synthetic_only', 'scope', 'status', 'dispatch', 'remote_effects',
                'local_cleanup_verified', 'response', 'events'}
    if (type(value) is not dict or not required <= set(value)
            or not set(value) <= required | {'elapsed_seconds', 'error', 'terminal_observed'}
            or value['synthetic_only'] is not True or value['scope'] != 'disposable-loopback-probe'
            or type(value['status']) is not str or value['status'] not in STATUSES
            or value['dispatch'] not in ('NOT_STARTED', 'UNKNOWN', 'SENT')
            or value['remote_effects'] != 'UNKNOWN' or type(value['local_cleanup_verified']) is not bool
            or (not value['local_cleanup_verified'] and value['status'] != 'CLEANUP_FAILED')
            or type(value['events']) is not list or not 1 <= len(value['events']) <= 8
            or any(type(e) is not str or e not in STATUSES | {'PREPARED', 'WORKER_STARTED', 'CONNECTING', 'REQUEST_SENT', 'CANCELLED_BEFORE_START'} for e in value['events'])):
        raise ValueError('Invalid probe evidence')
    events = value['events']
    if events == ['PREPARED', 'CANCELLED_BEFORE_START']:
        if value['status'] != 'CANCELLED' or value['dispatch'] != 'NOT_STARTED' or 'error' in value:
            raise ValueError('Invalid pre-start cancellation')
    else:
        stages = ['PREPARED', 'WORKER_STARTED', 'CONNECTING', 'REQUEST_SENT']
        if (len(events) < 3 or events[:-1] != stages[:len(events)-1] or events[-1] != value['status']
                or value['dispatch'] != ('SENT' if 'REQUEST_SENT' in events else 'UNKNOWN')):
            raise ValueError('Invalid probe lifecycle ordering')
    if value['local_cleanup_verified'] != (value['status'] != 'CLEANUP_FAILED'):
        raise ValueError('Invalid cleanup state')
    if 'error' in value and value['status'] not in {'FAILED', 'CLEANUP_FAILED'}:
        raise ValueError('Invalid error status')
    if value['status'] == 'COMPLETED':
        if (not value['local_cleanup_verified'] or value['dispatch'] != 'SENT'
                or type(value['response']) is not dict
                or set(value['response']) != {'synthetic_only', 'probe_id', 'value'}
                or value['response']['synthetic_only'] is not True
                or value['response']['probe_id'] != attempt_id or value['response']['value'] != 'ok'):
            raise ValueError('Unbound probe response')
    elif value['response'] is not None:
        raise ValueError('Unconfirmed response must not be retained')
    if 'elapsed_seconds' in value:
        elapsed = value['elapsed_seconds']
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('Invalid elapsed time')
    if 'terminal_observed' in value and (value['terminal_observed'] != 'RESPONSE_AFTER_BUDGET' or value['status'] not in {'TIMED_OUT', 'CLEANUP_FAILED'}):
        raise ValueError('Invalid late response marker')
    if 'error' in value:
        error = value['error']
        if (type(error) is not dict or set(error) != {'type', 'stage', 'errno', 'winerror'}
                or type(error['type']) is not str or re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', error['type']) is None
                or error['stage'] not in ('CONNECT_OR_SEND', 'READ_RESPONSE', 'VALIDATE_RESPONSE')
                or any(error[k] is not None and (type(error[k]) is not int or abs(error[k]) > 2**31) for k in ('errno', 'winerror'))):
            raise ValueError('Invalid failure evidence')

def execute_probe(store, port, *, request_key, timeout=5.0, cancel=None, runner=probe):
    from .storage import ExecutionConflict
    config = {'kind': 'disposable-loopback-probe', 'port': port, 'timeout': timeout}
    attempt, claimed = store.claim_probe(config, request_key)
    if not claimed:
        if attempt['state'] != 'RECORDED':
            raise ExecutionConflict('Probe intent is incomplete; replay prohibited')
        return attempt['outcome']
    # Exceptions and unconfirmed writes deliberately leave the committed intent
    # INCOMPLETE, preventing a retry from silently repeating an unknown request.
    outcome = runner(port, timeout=timeout, cancel=cancel, probe_id=attempt['attempt_id'])
    validate_outcome(outcome, attempt['attempt_id'])
    store.record_probe(attempt['attempt_id'], outcome)
    return outcome
