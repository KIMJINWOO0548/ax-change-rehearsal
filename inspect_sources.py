#!/usr/bin/env python3
"""Inspect cited changes in registered authored synthetic Markdown policies."""
import argparse
import json
import sys
from rehearsal.source_evidence import inspect_policy_sources


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy-version', required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect_policy_sources(args.policy_version)
    except (ValueError, OSError, RuntimeError):
        print(json.dumps({'error': 'SOURCE_EVIDENCE_UNAVAILABLE',
                          'message': 'Registered source evidence could not be verified.'}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
