#!/usr/bin/env python3
"""Create, inspect and restore local synthetic evidence backups only.

No network service, encryption, signatures, identity, or deployment approval.
"""
import argparse
import json
import sys

from rehearsal.recovery import create_backup, inspect_backup, restore_backup, rollover_workspace, RecoveryError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    backup = commands.add_parser('backup', help='Create a verified backup in a new private directory')
    backup.add_argument('--workspace', required=True)
    backup.add_argument('--destination', required=True)
    inspect = commands.add_parser('inspect', help='Read-only verification; does not authenticate the backup')
    inspect.add_argument('--source', required=True)
    restore = commands.add_parser('restore', help='Restore into a new private workspace; never overwrite')
    restore.add_argument('--source', required=True)
    restore.add_argument('--destination', required=True)
    rollover = commands.add_parser('rollover', help='Stop writer, archive current segment and create a new empty workspace')
    rollover.add_argument('--workspace', required=True)
    rollover.add_argument('--archive', required=True)
    rollover.add_argument('--destination', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'backup':
            result = create_backup(args.workspace, args.destination)
        elif args.command == 'inspect':
            result = inspect_backup(args.source)
        elif args.command == 'rollover':
            result = rollover_workspace(args.workspace, args.archive, args.destination)
        else:
            result = restore_backup(args.source, args.destination)
        print(json.dumps({'operation': args.command, 'status': 'VERIFIED',
                          'deployment_approval': False, **result}, ensure_ascii=False,
                         allow_nan=False, indent=2))
        return 0
    except (RecoveryError, ValueError, OSError, RuntimeError):
        print(json.dumps({'error': 'RECOVERY_UNAVAILABLE',
                          'message': 'Backup or recovery could not be verified. Preserve existing data and review locally.'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
