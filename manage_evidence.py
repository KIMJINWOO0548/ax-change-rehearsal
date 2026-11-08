#!/usr/bin/env python3
"""Inspect and explicitly replay an existing local synthetic evidence store."""
import argparse
import json
from pathlib import Path
import sys

from rehearsal.replay import replay_report
from rehearsal.storage import EvidenceStore, StorageError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('verify', help='Verify every saved report and review hash chain')
    commands.add_parser('list', help='List saved IDs and scope, without notes or raw inputs')
    replay = commands.add_parser('replay', help='Explicitly replay a registered synthetic run; does not save')
    replay.add_argument('run_id')
    args = parser.parse_args(argv)
    try:
        workspace = Path(args.workspace)
        if not workspace.is_dir() or not (workspace / 'evidence.sqlite3').is_file():
            raise StorageError('Existing workspace required')
        store = EvidenceStore(workspace)
        if args.command == 'replay':
            output = replay_report(store.get(args.run_id)['report'])
            code = 0 if output['status'] == 'MATCH' else 2
        else:
            runs = store.list_runs()
            output = {'integrity': 'VERIFIED', 'runs': len(runs), 'authenticated_audit': False,
                      'deployment_approval': False}
            if args.command == 'list':
                output['records'] = [{key: run[key] for key in
                    ('run_id', 'sha256', 'revision', 'review_status', 'scope', 'readiness')} for run in runs]
            code = 0
        print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
        return code
    except (StorageError, ValueError, RuntimeError, OSError):
        # Do not include local path, notes, raw data, or exception tracebacks.
        print(json.dumps({'error': 'EVIDENCE_UNAVAILABLE',
                          'message': 'Cannot verify or replay this workspace. Preserve it and review locally.'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
