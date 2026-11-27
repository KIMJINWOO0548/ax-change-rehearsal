"""Connect the Windows application to a private instance of the synthetic workbench."""

import re
import sys
from threading import Thread

from rehearsal.server import make_server
from rehearsal.storage import StorageError


def main():
    token = sys.stdin.buffer.readline(65)
    if len(sys.argv) != 2 or not re.fullmatch(rb'[0-9A-F]{64}\n', token):
        return 2
    try:
        with make_server(0, workspace=sys.argv[1], desktop_session=token[:-1].decode('ascii')) as workbench:
            workbench.daemon_threads = False

            def stop_on_host_exit():
                sys.stdin.buffer.read(1)
                workbench.shutdown()

            Thread(target=stop_on_host_exit, daemon=True).start()
            print(workbench.server_port, flush=True)
            workbench.serve_forever()
    except (OSError, StorageError):
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
