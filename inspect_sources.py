#!/usr/bin/env python3
"""Inspect cited changes in registered fixtures or explicitly selected local Markdown."""
import argparse
import json
import sys
from rehearsal.source_evidence import inspect_policy_sources, inspect_local_sources
from rehearsal.change_candidates import build_change_candidates


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--policy-version')
    mode.add_argument('--before', help='Explicit local UTF-8 Markdown source; printed text stays on stdout')
    parser.add_argument('--after', help='Local UTF-8 Markdown replacement; requires --before')
    parser.add_argument('--candidates', action='store_true', help='Add cited, unreviewed lexical change candidates')
    args = parser.parse_args(argv)
    if bool(args.before) != bool(args.after):
        parser.error('Use both --before and --after, or only --policy-version')
    try:
        result = (inspect_local_sources(args.before, args.after) if args.before
                  else inspect_policy_sources(args.policy_version))
        if args.candidates:
            result = {**result, 'change_candidates': build_change_candidates(result)}
    except (ValueError, OSError, RuntimeError):
        print(json.dumps({'error': 'SOURCE_EVIDENCE_UNAVAILABLE',
                          'message': 'Source evidence could not be verified.'}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
