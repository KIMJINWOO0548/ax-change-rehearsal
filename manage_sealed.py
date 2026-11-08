#!/usr/bin/env python3
"""Seal verified local synthetic backups with optional authenticated encryption.

Requires Python 3.10+ and requirements-encryption.txt.
Passphrases are entered in a local hidden terminal, never arguments or files.
Original workspaces/plaintext backups remain unchanged and unencrypted.
"""
import argparse
import getpass
import hmac
import json
import sys
import warnings

from rehearsal.sealed import seal_backup, inspect_sealed, restore_sealed, SealedError, SealedDependencyError, check_support


def _passphrase(confirm=False):
    # getpass otherwise warns and falls back to echoed stdin. Fail closed.
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError('A hidden local terminal is required')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        value = getpass.getpass('Passphrase (hidden; never saved): ')
        encoded = value.encode('utf-8')
        if len(value) < 12 or len(encoded) > 1024:
            raise ValueError('Invalid passphrase length')
        if confirm:
            repeated = getpass.getpass('Confirm passphrase (hidden): ').encode('utf-8')
            if not hmac.compare_digest(encoded, repeated):
                raise ValueError('Passphrases did not match')
    return encoded


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unknown arguments, which could contain a
        # mistakenly supplied passphrase or private path. Never print them.
        self.exit(2, 'Invalid command or arguments. Use --help; never pass a password as an argument.\n')


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    seal = sub.add_parser('seal', help='Seal a validated plaintext bundle into a new file')
    seal.add_argument('--source', required=True)
    seal.add_argument('--destination', required=True)
    inspect = sub.add_parser('inspect', help='Authenticate and inspect without plaintext output')
    inspect.add_argument('--source', required=True)
    restore = sub.add_parser('restore', help='Authenticate, validate and restore a NEW private workspace')
    restore.add_argument('--source', required=True)
    restore.add_argument('--destination', required=True)
    args = parser.parse_args(argv)
    try:
        check_support()
        secret = _passphrase(confirm=args.command == 'seal')
        if args.command == 'seal':
            result = seal_backup(args.source, args.destination, secret)
        elif args.command == 'inspect':
            result = inspect_sealed(args.source, secret)
        else:
            result = restore_sealed(args.source, args.destination, secret)
        print(json.dumps({'operation': args.command, 'status': result.get('verification', 'VERIFIED'),
                          'deployment_approval': False, **result}, ensure_ascii=False,
                         allow_nan=False, indent=2))
        return 0
    except SealedDependencyError:
        print(json.dumps({'error': 'SEALED_FEATURE_UNAVAILABLE',
                          'message': 'Install the locked optional encryption dependencies in a supported Python 3.10+ environment.'}), file=sys.stderr)
        return 1
    except (SealedError, ValueError, UnicodeError, OSError, EOFError,
            getpass.GetPassWarning, KeyboardInterrupt):
        # Do not distinguish wrong passwords from altered ciphertext, expose
        # paths or exception text, or allow fallback to echoed stdin.
        print(json.dumps({'error': 'SEALED_OPERATION_UNAVAILABLE',
                          'message': 'Could not verify this sealed operation. Use a supported local hidden terminal and preserve existing files.'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
