"""`scu` command line interface.

Every command prints a single JSON object to stdout so any agent can parse
the result. Errors exit non-zero with {"ok": false, "error": ...}.
"""

import argparse
import datetime
import json
import os
import signal
import subprocess
import sys
import time

from scu import __version__, actions, config, screens, state


def ok(**kw):
    print(json.dumps({"ok": True, **kw}))


def fail(msg, **kw):
    print(json.dumps({"ok": False, "error": msg, **kw}))
    sys.exit(1)


def _parse_xy(s):
    try:
        x, y = s.split(",") if "," in s else s.split()
        return float(x), float(y)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected 'x,y' got {s!r}")


# ---------------------------------------------------------------- overlay --


def _overlay_pid():
    try:
        with open(config.OVERLAY_PID_PATH) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError, FileNotFoundError):
        return None


def glow_start():
    if _overlay_pid():
        return True
    config.ensure_dirs()
    log = open(config.OVERLAY_LOG_PATH, "ab")
    subprocess.Popen(
        [sys.executable, "-m", "scu.overlay.daemon"],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(50):
        if _overlay_pid():
            return True
        time.sleep(0.1)
    return False


def glow_stop():
    pid = _overlay_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(15):
            if not _overlay_pid():
                break
            time.sleep(0.1)
        if _overlay_pid():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    try:
        os.remove(config.OVERLAY_PID_PATH)
    except OSError:
        pass
    return True


# ---------------------------------------------------------------- commands --


def cmd_screenshot(args):
    ds = screens.displays()
    targets = ds if args.screen == "all" else [screens.get_display(args.screen)]
    out_dir = args.out or config.SHOTS_DIR
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shots = []
    for d in targets:
        png = screens.screenshot(d)
        path = os.path.join(out_dir, f"screen{d.index}-{ts}.png")
        with open(path, "wb") as f:
            f.write(png)
        shots.append({"screen": d.index, "path": path, **d.to_dict()})
    state.update(status="Screenshot", session=state.session_active())
    ok(screenshots=shots, displays=[d.to_dict() for d in ds])


def cmd_ground(args):
    from scu import grounding

    disp = screens.get_display(args.screen)
    shot = screens.screenshot(disp)
    try:
        fx, fy, raw = grounding.ground(args.desc, shot)
    except grounding.GroundingError as e:
        fail(str(e))
    x, y = screens.fraction_to_point(fx, fy, disp)
    state.update(status=f"Grounded '{args.desc}'", screen=disp.display_id)
    ok(x=x, y=y, screen=disp.index, fx=round(fx, 4), fy=round(fy, 4), raw=raw)


def cmd_click(args):
    at = _parse_xy(args.at) if args.at else None
    hold = args.hold.split(",") if args.hold else []
    r = actions.click(
        desc=args.desc,
        at=at,
        screen=args.screen,
        num_clicks=args.clicks,
        button=args.button,
        hold=hold,
    )
    ok(**r)


def cmd_type(args):
    at = _parse_xy(args.at) if args.at else None
    r = actions.type_text(
        text=args.text,
        into=args.into,
        at=at,
        screen=args.screen,
        overwrite=args.overwrite,
        enter=args.enter,
    )
    ok(**r)


def cmd_scroll(args):
    at = _parse_xy(args.at) if args.at else None
    r = actions.scroll(
        clicks=args.clicks,
        on=args.on,
        at=at,
        screen=args.screen,
        horizontal=args.horizontal,
    )
    ok(**r)


def cmd_drag(args):
    from_at = _parse_xy(args.from_at) if args.from_at else None
    to_at = _parse_xy(args.to_at) if args.to_at else None
    r = actions.drag(
        from_desc=args.frm,
        to_desc=args.to,
        from_at=from_at,
        to_at=to_at,
        screen=args.screen,
        hold=args.hold.split(",") if args.hold else [],
    )
    ok(**r)


def cmd_find_text(args):
    from scu import ocr

    ds = screens.displays()
    targets = ds if args.screen == "all" else [screens.get_display(args.screen)]
    results = []
    for d in targets:
        shot = screens.screenshot(d)
        for m in ocr.find(args.phrase, shot, limit=args.limit):
            x, y = screens.fraction_to_point(m["fx"], m["fy"], d)
            results.append(
                {**m, "x": x, "y": y, "screen": d.index}
            )
    results.sort(key=lambda m: -m["score"])
    state.update(status=f"Find text '{args.phrase}'")
    ok(phrase=args.phrase, matches=results[: args.limit])


def cmd_session(args):
    if args.sub == "start":
        state.update(session=True, status="Session started")
        started = glow_start()
        ok(session=True, overlay=started)
    else:
        state.update(session=False, status="")
        glow_stop()
        ok(session=False, overlay=False)


def cmd_glow(args):
    if args.sub == "start":
        state.update(session=True)
        ok(overlay=glow_start())
    elif args.sub == "stop":
        state.update(session=False)
        glow_stop()
        ok(overlay=False)
    else:
        ok(overlay=bool(_overlay_pid()), session=state.session_active())


def cmd_status(args):
    state.update(status=args.message)
    ok(status=args.message)


def cmd_ground_server(args):
    from scu import grounding

    if args.sub == "serve":
        cfg = config.grounding_config()
        if not grounding.local_installed():
            fail("mlx-vlm not installed; run `scu install` or "
                 "pip install 'simple-computer-use[local]'")
        model = cfg.get("local_model") or config.DEFAULT_LOCAL_MODEL
        port = cfg.get("local_port", config.DEFAULT_LOCAL_PORT)
        print(f"serving {model} on http://127.0.0.1:{port} (foreground)")
        os.execvp(sys.executable, [
            sys.executable, "-m", "mlx_vlm.server",
            "--model", model, "--host", "127.0.0.1", "--port", str(port),
        ])
    else:
        cfg = config.grounding_config()
        url = f"http://127.0.0.1:{cfg.get('local_port', config.DEFAULT_LOCAL_PORT)}"
        ok(running=grounding._server_alive(url), url=url)


def cmd_mcp(args):
    try:
        from scu import mcp_server
    except ImportError:
        fail("mcp extra not installed: pip install 'simple-computer-use[mcp]'")
    mcp_server.run()


def build_parser():
    p = argparse.ArgumentParser(
        prog="scu",
        description="simple-computer-use — computer-use tools for any agent",
    )
    p.add_argument("--version", action="version", version=f"scu {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def _common_target(sp, desc_arg=True):
        if desc_arg:
            sp.add_argument("desc", nargs="?", default=None,
                            help="element description (grounded) or visible text (OCR)")
        sp.add_argument("--at", default=None, help="global point 'x,y'")
        sp.add_argument("--screen", default=None,
                        help="display index (default: primary) or 'all'")

    sp = sub.add_parser("screenshot", help="capture display(s) to PNG files")
    sp.add_argument("--screen", default=None, help="index (default primary) or 'all'")
    sp.add_argument("--out", default=None, help="output directory")
    sp.set_defaults(fn=cmd_screenshot)

    sp = sub.add_parser("ground", help="resolve a description to coordinates")
    sp.add_argument("desc")
    sp.add_argument("--screen", default=None)
    sp.set_defaults(fn=cmd_ground)

    sp = sub.add_parser("click", help="click an element")
    _common_target(sp)
    sp.add_argument("--clicks", type=int, default=1)
    sp.add_argument("--button", default="left", choices=["left", "right", "middle"])
    sp.add_argument("--hold", default="", help="comma-separated keys to hold")
    sp.set_defaults(fn=cmd_click)

    sp = sub.add_parser("type", help="type text, optionally into an element")
    sp.add_argument("text")
    sp.add_argument("--into", default=None, help="element description to click first")
    sp.add_argument("--at", default=None)
    sp.add_argument("--screen", default=None)
    sp.add_argument("--overwrite", action="store_true")
    sp.add_argument("--enter", action="store_true")
    sp.set_defaults(fn=cmd_type)

    sp = sub.add_parser("scroll", help="scroll up (+N) / down (-N) / horizontal")
    sp.add_argument("clicks", type=int)
    sp.add_argument("--on", default=None, help="element description")
    sp.add_argument("--at", default=None)
    sp.add_argument("--screen", default=None)
    sp.add_argument("--horizontal", action="store_true")
    sp.set_defaults(fn=cmd_scroll)

    sp = sub.add_parser("drag", help="drag between two points/elements")
    sp.add_argument("frm", nargs="?", default=None)
    sp.add_argument("to", nargs="?", default=None)
    sp.add_argument("--from", dest="from_at", default=None)
    sp.add_argument("--to", dest="to_at", default=None)
    sp.add_argument("--screen", default=None)
    sp.add_argument("--hold", default="")
    sp.set_defaults(fn=cmd_drag)

    sp = sub.add_parser("hotkey", help="press a key combo: scu hotkey cmd shift s")
    sp.add_argument("keys", nargs="+")
    sp.set_defaults(fn=lambda a: ok(**actions.hotkey(a.keys)))

    sp = sub.add_parser("press", help="press a single key")
    sp.add_argument("key")
    sp.add_argument("--presses", type=int, default=1)
    sp.set_defaults(fn=lambda a: ok(**actions.press(a.key, a.presses)))

    sp = sub.add_parser("open", help="open an app or file by name")
    sp.add_argument("name")
    sp.set_defaults(fn=lambda a: ok(**actions.open_app(a.name)))

    sp = sub.add_parser("focus", help="bring an app to the front")
    sp.add_argument("name")
    sp.set_defaults(fn=lambda a: ok(**actions.focus_app(a.name)))

    sp = sub.add_parser("find-text", help="OCR-locate text on screen")
    sp.add_argument("phrase")
    sp.add_argument("--screen", default=None, help="index or 'all'")
    sp.add_argument("--limit", type=int, default=5)
    sp.set_defaults(fn=cmd_find_text)

    sp = sub.add_parser("wait", help="sleep N seconds")
    sp.add_argument("seconds", type=float)
    sp.set_defaults(fn=lambda a: ok(**actions.wait(a.seconds)))

    sp = sub.add_parser("status", help="set overlay status text")
    sp.add_argument("message")
    sp.set_defaults(fn=cmd_status)

    sp = sub.add_parser("session", help="start/end a computer-use session")
    sp.add_argument("sub", choices=["start", "end"])
    sp.set_defaults(fn=cmd_session)

    sp = sub.add_parser("glow", help="overlay control")
    sp.add_argument("sub", choices=["start", "stop", "status"])
    sp.set_defaults(fn=cmd_glow)

    sp = sub.add_parser("ground-server", help="manage the local grounding server")
    sp.add_argument("sub", choices=["serve", "status"])
    sp.set_defaults(fn=cmd_ground_server)

    sp = sub.add_parser("mcp", help="run the MCP stdio server")
    sp.set_defaults(fn=cmd_mcp)

    sp = sub.add_parser("doctor", help="check deps, permissions, grounding")
    sp.set_defaults(fn=lambda a: __import__("scu.doctor", fromlist=["run"]).run())

    sp = sub.add_parser("agents", help="list detected agents")
    sp.set_defaults(
        fn=lambda a: __import__("scu.installer", fromlist=["cmd_agents"]).cmd_agents(a)
    )

    sp = sub.add_parser("install", help="install skills into detected agents")
    sp.add_argument("--agent", default=None, help="agent id or 'all'")
    sp.add_argument("--grounding", default=None,
                    choices=["local", "remote", "none"],
                    help="skip the grounding prompt")
    sp.add_argument("--yes", action="store_true", help="non-interactive defaults")
    sp.set_defaults(
        fn=lambda a: __import__("scu.installer", fromlist=["cmd_install"]).cmd_install(a)
    )

    sp = sub.add_parser("uninstall", help="remove installed skills")
    sp.add_argument("--agent", default=None)
    sp.set_defaults(
        fn=lambda a: __import__("scu.installer", fromlist=["cmd_uninstall"]).cmd_uninstall(a)
    )

    return p


def main():
    args = build_parser().parse_args()
    try:
        args.fn(args)
    except KeyboardInterrupt:
        fail("interrupted")
    except SystemExit:
        raise
    except Exception as e:
        fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
