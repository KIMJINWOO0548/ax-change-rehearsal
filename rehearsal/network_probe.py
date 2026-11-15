"""Opt-in HTTP boundary probe for a disposable loopback service only.

Not registered as a business adapter. Cancellation stops the local worker, never
proves that a remote request was cancelled or that remote state is unchanged.
"""
from __future__ import annotations
import http.client
import json
import math
import multiprocessing
import time
import uuid
from .validation import _reject_constant, _unique_pairs

PATH = '/ax-rehearsal/v1/probe'
MAX_RESPONSE = 8192

def _worker(channel, port, probe_id, timeout):
    connection = None
    stage = 'CONNECT_OR_SEND'
    try:
        channel.send(('stage', 'CONNECTING'))
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
        # Fixed GET, no credentials, body, redirects, proxy, DNS or arbitrary URL.
        connection.request('GET', PATH, headers={'X-Probe-ID': probe_id, 'Accept': 'application/json'})
        channel.send(('stage', 'REQUEST_SENT'))
        stage = 'READ_RESPONSE'
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError('Non-success status')
        payload = response.read(MAX_RESPONSE + 1)
        if len(payload) > MAX_RESPONSE:
            raise ValueError('Response limit exceeded')
        stage = 'VALIDATE_RESPONSE'
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
        if (type(value) is not dict or set(value) != {'synthetic_only', 'probe_id', 'value'}
                or value['synthetic_only'] is not True or value['probe_id'] != probe_id
                or value['value'] != 'ok'):
            raise ValueError('Unverified probe response')
        channel.send(('result', value))
    except Exception as exc:
        # No raw response, URL or local exception text in exported evidence.
        try:
            channel.send(('failure', {'type': type(exc).__name__, 'stage': stage,
                                      'errno': getattr(exc, 'errno', None),
                                      'winerror': getattr(exc, 'winerror', None)}))
        except (BrokenPipeError, EOFError, OSError):
            pass  # Parent already cancelled/closed; do not leak a worker traceback.
    finally:
        if connection is not None:
            connection.close()
        channel.close()

def probe(port, *, timeout=5.0, cancel=None, probe_id=None):
    """Bounded local-network probe. Call only for a service you own for testing.

    Deadline budget includes spawn/network/parse; OS process operations are not preemptible.
    Cleanup joins add up to 1.7 seconds under normal OS scheduling; no hard realtime guarantee.
    No automatic retry. Caller cancellation must expose threading.Event.is_set().
    Returned evidence is not an authenticated or durable business execution log.
    """
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not .05 <= timeout <= 30:
        raise ValueError('Invalid deadline')
    if probe_id is None: probe_id = uuid.uuid4().hex
    if type(probe_id) is not str or len(probe_id) != 32 or any(c not in '0123456789abcdef' for c in probe_id):
        raise ValueError('Invalid probe ID')
    started = time.monotonic()
    result = {'synthetic_only': True, 'scope': 'disposable-loopback-probe',
              'status': 'FAILED', 'dispatch': 'NOT_STARTED', 'remote_effects': 'UNKNOWN',
              'local_cleanup_verified': True, 'response': None, 'events': ['PREPARED']}
    if cancel is not None and cancel.is_set():
        return {**result, 'status': 'CANCELLED', 'events': ['PREPARED', 'CANCELLED_BEFORE_START']}
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    worker = context.Process(target=_worker, args=(sender, port, probe_id, timeout), daemon=True)
    spawned = False
    try:
        worker.start(); spawned = True; sender.close()
        # Even before REQUEST_SENT is observed, partial send cannot be ruled out.
        result['dispatch'] = 'UNKNOWN'
        result['events'].append('WORKER_STARTED')
        deadline = started + timeout
        while True:
            terminal = False
            # Worker emits at most two stages plus one terminal message. Drain only
            # already-ready messages, never wait for a terminal before cancellation.
            for _ in range(4):
                if not receiver.poll(0): break
                try: kind, value = receiver.recv()
                except EOFError:
                    terminal = True; break
                if kind == 'stage':
                    result['events'].append(value)
                    if value == 'REQUEST_SENT': result['dispatch'] = 'SENT'
                elif kind == 'result':
                    if time.monotonic() >= deadline:
                        result['status'] = 'TIMED_OUT'
                        result['terminal_observed'] = 'RESPONSE_AFTER_BUDGET'
                    else:
                        result['response'] = value; result['status'] = 'COMPLETED'
                    terminal = True; break
                elif kind == 'failure':
                    result['error'] = value; terminal = True; break
            if terminal: break
            if cancel is not None and cancel.is_set():
                result['status'] = 'CANCELLED'; break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result['status'] = 'TIMED_OUT'; break
            if not worker.is_alive() and not receiver.poll(0): break
            receiver.poll(min(.02, remaining))
    finally:
        sender.close(); receiver.close()
        if spawned:
            # A failed termination syscall must not skip the stronger fallback
            # or turn unverified cleanup into success. Observe liveness after
            # each bounded attempt; never infer remote cancellation from it.
            try: worker.join(.1)
            except OSError: pass
            for stop in (worker.terminate, worker.kill):
                if not worker.is_alive(): break
                try: stop()
                except OSError: pass
                try: worker.join(.8)
                except OSError: pass
            result['local_cleanup_verified'] = not worker.is_alive()
            if result['local_cleanup_verified']: worker.close()
        if not result['local_cleanup_verified']:
            result['status'] = 'CLEANUP_FAILED'; result['response'] = None
        result['events'].append(result['status'])
        result['elapsed_seconds'] = round(time.monotonic() - started, 4)
    return result

def main(argv=None):
    import argparse
    import signal
    import threading
    parser = argparse.ArgumentParser(description='Probe a disposable loopback test service only; not a business connector.')
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--timeout', type=float, default=5)
    parser.add_argument('--workspace', help='Existing evidence workspace for durable diagnostic intent')
    parser.add_argument('--request-key', help='Non-secret stable retry key; required with --workspace')
    args = parser.parse_args(argv)
    if bool(args.workspace) != bool(args.request_key):
        parser.error('--workspace and --request-key must be provided together')
    cancelled = threading.Event()
    previous = signal.signal(signal.SIGINT, lambda *_: cancelled.set())
    try:
        if args.workspace:
            from .storage import EvidenceStore
            from .probe_journal import execute_probe
            value = execute_probe(EvidenceStore(args.workspace), args.port, request_key=args.request_key, timeout=args.timeout, cancel=cancelled)
        else:
            value = probe(args.port, timeout=args.timeout, cancel=cancelled)
        print(json.dumps(value, ensure_ascii=True, sort_keys=True))
        return 0 if value['status'] == 'COMPLETED' else 2
    finally:
        signal.signal(signal.SIGINT, previous)

if __name__ == '__main__':
    raise SystemExit(main())
