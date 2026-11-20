#!/usr/bin/env python3
"""Record and check explicit local source-review statements; never grant approval."""
import argparse
import json
import sys
from rehearsal.source_review import record_review, verify_review


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    record = commands.add_parser('record')
    record.add_argument('--destination', required=True)
    record.add_argument('--reviewer', required=True)
    record.add_argument('--status', choices=['REVIEWED', 'CHANGES_REQUESTED'], required=True)
    record.add_argument('--note', default='')
    verify = commands.add_parser('verify')
    verify.add_argument('--source', required=True)
    for command in (record, verify):
        command.add_argument('--before', required=True)
        command.add_argument('--after', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'record':
            result = record_review(args.before, args.after, args.destination,
                                   reviewer=args.reviewer, status=args.status, note=args.note)
        else:
            result = verify_review(args.source, args.before, args.after)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 2 if result.get('binding') == 'STALE' else 0
    except (ValueError, OSError, RuntimeError):
        print(json.dumps({'error': 'SOURCE_REVIEW_UNAVAILABLE',
                          'message': 'Preserve the inputs and review record; verification or save failed.'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
