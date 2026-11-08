#!/usr/bin/env python3
"""Run the synthetic workbench on loopback only, without third-party packages."""
import argparse
from rehearsal.server import make_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    with make_server(args.port) as server:
        print(f'Open http://127.0.0.1:{server.server_port}', flush=True)
        print('Local synthetic workbench only. Press Ctrl+C to stop.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
