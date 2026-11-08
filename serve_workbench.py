#!/usr/bin/env python3
"""Run the synthetic workbench on loopback only, without third-party packages."""
import argparse
from rehearsal.server import make_server
from rehearsal.storage import StorageError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--workspace', help='Opt-in private directory for local synthetic evidence (default: ephemeral)')
    args = parser.parse_args()
    try:
        instance = make_server(args.port, workspace=args.workspace)
    except StorageError:
        parser.exit(2, 'Local evidence unavailable: use a private, owned directory with an intact ledger. No permissions were changed.\n')
    with instance as server:
        print(f'Open http://127.0.0.1:{server.server_port}', flush=True)
        print('Local synthetic workbench only. Press Ctrl+C to stop.', flush=True)
        print('Evidence: local synthetic persistence enabled; no authentication, encryption, signatures or approval.' if args.workspace else 'Evidence: ephemeral (not saved).', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
