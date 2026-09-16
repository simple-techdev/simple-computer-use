"""Overlay daemon entry point: `python -m scu.overlay.daemon`.

Spawned detached by `scu session start` / `scu glow start`. Renders the
orange glow on active displays plus the agent cursor badge, then exits when
the session flag clears or it receives SIGTERM.
"""

import os
import signal
import sys

from scu import config, state


def _write_pid():
    config.ensure_dirs()
    with open(config.OVERLAY_PID_PATH, "w") as f:
        f.write(str(os.getpid()))


def _remove_pid():
    try:
        os.remove(config.OVERLAY_PID_PATH)
    except OSError:
        pass


def main():
    _write_pid()

    def _term(*_):
        # os._exit: a raised SystemExit here would be swallowed by the ObjC
        # callback bridge and re-armed on every tick, never exiting.
        os._exit(0)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)
    try:
        if sys.platform == "darwin":
            from scu.overlay import macos

            macos.run()
        else:
            from scu.overlay import generic

            generic.run()
    finally:
        _remove_pid()


if __name__ == "__main__":
    main()
