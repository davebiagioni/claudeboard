from __future__ import annotations

import os
import signal
import subprocess
import sys

from claudeboard.server import PORT, run

USAGE = "usage: claudeboard [start|stop]"


def _stop() -> int:
    out = subprocess.run(
        ["lsof", f"-tiTCP:{PORT}", "-sTCP:LISTEN", "-nP"],
        capture_output=True,
        text=True,
    )
    pids = [int(p) for p in out.stdout.split() if p.strip().isdigit()]
    if not pids:
        print(f"claudeboard not running on port {PORT}")
        return 0
    for pid in pids:
        os.kill(pid, signal.SIGTERM)
        print(f"stopped pid {pid}")
    return 0


def main() -> None:
    args = sys.argv[1:]
    if not args or args == ["start"]:
        run()
        return
    if args == ["stop"]:
        sys.exit(_stop())
    print(USAGE, file=sys.stderr)
    sys.exit(2)
