#!/usr/bin/env python3
"""Read-only comparison of explicit local JSON sources; stdout contains source values."""
import argparse
import json
import sys
from rehearsal.json_sources import inspect_json_sources


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument('--candidates', action='store_true', help='Include unreviewed typed JSON changes')
    args = parser.parse_args(argv)
    try:
        result = inspect_json_sources(args.before, args.after, candidates=args.candidates)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError):
        print(json.dumps({'error': 'JSON_SOURCE_UNAVAILABLE',
                          'message': 'Local JSON evidence could not be verified.'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
