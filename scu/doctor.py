"""`scu doctor` — environment health check."""

import json
import shutil
import sys

from scu import config, grounding, screens


def _check(label, ok, detail=""):
    mark = "✓" if ok else ("·" if ok is None else "✗")
    print(f"  [{mark}] {label:<28} {detail}")
    return ok


def run(json_out: bool = False):
    from scu import installer

    results = {}
    print("simple-computer-use doctor\n")

    # deps
    print("Dependencies")
    for mod, pkg in [
        ("pyautogui", "pyautogui"),
        ("PIL", "pillow"),
        ("pytesseract", "pytesseract"),
        ("pyperclip", "pyperclip"),
        ("requests", "requests"),
    ]:
        try:
            __import__(mod)
            results[pkg] = _check(pkg, True)
        except ImportError:
            results[pkg] = _check(pkg, False, "pip install " + pkg)

    if sys.platform == "darwin":
        try:
            import Quartz, AppKit  # noqa

            results["pyobjc"] = _check("pyobjc (overlay+screens)", True)
        except ImportError:
            results["pyobjc"] = _check("pyobjc", False, "pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz")

    tess = shutil.which("tesseract")
    results["tesseract"] = _check("tesseract", bool(tess), tess or "brew install tesseract")

    # displays
    print("\nDisplays")
    ds = screens.displays()
    for d in ds:
        _check(f"display {d.index}{' (primary)' if d.primary else ''}",
               True, f"{d.w}x{d.h} @({d.x},{d.y}) scale {d.scale:g}")
    results["displays"] = len(ds)

    # permissions
    print("\nPermissions")
    perms = installer.check_permissions()
    for k, v in perms.items():
        label = "Screen Recording" if k == "screen_recording" else "Accessibility"
        results[k] = _check(label, v if v is not None else None,
                            "" if v else "grant in System Settings > Privacy & Security")

    # grounding
    print("\nGrounding")
    cfg = config.grounding_config()
    prov = cfg.get("provider", "none")
    _check("provider", True, prov)
    if prov == "local":
        results["mlx_vlm"] = _check(
            "mlx-vlm", grounding.local_installed(),
            "" if grounding.local_installed() else "pip install 'simple-computer-use[local]'")
        url = f"http://127.0.0.1:{cfg.get('local_port', config.DEFAULT_LOCAL_PORT)}"
        alive = grounding._server_alive(url)
        results["ground_server"] = _check("local server", alive if alive else None,
                                          url + (" (running)" if alive else " (starts on first use)"))
    elif prov == "remote":
        url = cfg.get("url", "")
        try:
            import requests

            r = requests.get(url.rstrip("/") + "/v1/models", timeout=3)
            results["ground_remote"] = _check("remote endpoint", r.status_code < 500, url)
        except Exception as e:
            results["ground_remote"] = _check("remote endpoint", False, f"{url} ({e})")
    else:
        _check("endpoint", None, "none — use --at / find-text (run `scu install` to configure)")

    # screenshot smoke test
    print("\nSmoke test")
    try:
        png = screens.screenshot(ds[0])
        results["screenshot"] = _check("screenshot", len(png) > 10000,
                                     f"{len(png)//1024} KB captured")
    except Exception as e:
        results["screenshot"] = _check("screenshot", False, str(e))

    overlay = None
    try:
        if sys.platform == "darwin":
            import scu.overlay.macos  # noqa
        else:
            import scu.overlay.generic  # noqa
        overlay = True
    except Exception as e:
        overlay = str(e)
    print()
    results["overlay"] = _check("overlay UI", overlay is True, "" if overlay is True else str(overlay))

    hard_fail = [k for k in ("screen_recording", "accessibility", "screenshot")
                 if results.get(k) is False]
    if hard_fail:
        print(f"\nAction needed: {', '.join(hard_fail)} — then re-run `scu doctor`.")
    else:
        print("\nLooks good.")
    return results
