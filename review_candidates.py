#!/usr/bin/env python3
"""Save and verify explicit candidate dispositions locally; never approve deployment."""
import argparse
import json
import sys
from rehearsal.candidate_review import record_candidate_review, verify_candidate_review, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    record = commands.add_parser('record')
    record.add_argument('--destination', required=True)
    record.add_argument('--reviewer', required=True)
    record.add_argument('--decisions', required=True, help='Explicit local JSON list of candidate_id, decision, reason')
    verify = commands.add_parser('verify')
    verify.add_argument('--source', required=True)
    for command in (record, verify):
        command.add_argument('--before', required=True)
        command.add_argument('--after', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'record':
            result = record_candidate_review(args.before, args.after, args.destination,
                                             reviewer=args.reviewer, decisions=read_json(args.decisions))
        else:
            result = verify_candidate_review(args.source, args.before, args.after)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 2 if result.get('binding') == 'STALE' else 0
    except (ValueError, OSError, RuntimeError):
        print(json.dumps({'error': 'CANDIDATE_REVIEW_UNAVAILABLE',
                          'message': 'Preserve local inputs and records; review verification or save failed.'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
