"""`scu install` — one-shot setup:

1. Detect which agents live on this machine (binaries + config dirs)
2. Let the user pick one (or all) and install the skill / MCP / rules
3. Install OS-level deps (tesseract via brew, mlx-vlm for local grounding)
4. Configure grounding (local bundled model | remote endpoint | fallback)
5. Check macOS permissions and walk the user through granting them
"""

import os
import platform
import shutil
import subprocess
import sys
from typing import List, Optional

from scu import agents, config, grounding


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return ans or default


def _yes(prompt: str, default: bool = True, assume_yes: bool = False) -> bool:
    if assume_yes:
        return default
    ans = _ask(f"{prompt} (y/n)", "y" if default else "n")
    return ans.lower().startswith("y")


# ------------------------------------------------------------ dependencies --


def ensure_tesseract(assume_yes: bool = False) -> bool:
    if shutil.which("tesseract"):
        return True
    print("tesseract not found (needed for `find-text` / OCR fallback)")
    if sys.platform == "darwin" and shutil.which("brew"):
        if _yes("Install via Homebrew?", True, assume_yes):
            r = subprocess.run(["brew", "install", "tesseract"])
            if r.returncode == 0 and shutil.which("tesseract"):
                return True
        return False
    print("  install it manually: https://tesseract-ocr.github.io/tessdoc/Installation.html")
    return False


def _venv_pip_install(pkg: str) -> bool:
    """pip install into the interpreter running scu. pipx venvs ship without
    pip, so bootstrap it via ensurepip first when needed."""
    has_pip = (
        subprocess.run(
            [sys.executable, "-m", "pip", "--version"], capture_output=True
        ).returncode
        == 0
    )
    if not has_pip:
        subprocess.run([sys.executable, "-m", "ensurepip"], capture_output=True)
        has_pip = (
            subprocess.run(
                [sys.executable, "-m", "pip", "--version"], capture_output=True
            ).returncode
            == 0
        )
    if not has_pip:
        return False
    return (
        subprocess.run([sys.executable, "-m", "pip", "install", pkg]).returncode
        == 0
    )


def ensure_mlx_vlm() -> bool:
    if grounding.local_installed():
        return True
    print("Installing mlx-vlm (local grounding engine)...")
    installed = False
    if "pipx" in sys.prefix and shutil.which("pipx"):
        pkg = os.path.basename(sys.prefix.rstrip(os.sep))
        installed = (
            subprocess.run(["pipx", "inject", pkg, "mlx-vlm"]).returncode == 0
        )
    if not installed:
        installed = _venv_pip_install("mlx-vlm")
    if installed:
        import importlib

        importlib.invalidate_caches()
    return installed and grounding.local_installed()


def download_model(model: str) -> bool:
    print(f"Downloading {model} (~5 GB, one-time)...")
    r = subprocess.run(
        [
            sys.executable,
            "-c",
            "from huggingface_hub import snapshot_download; "
            f"snapshot_download({model!r}); print('done')",
        ]
    )
    return r.returncode == 0


# ------------------------------------------------------------- permissions --


def _cg_preflight(name: str) -> Optional[bool]:
    """CoreGraphics permission check via ctypes (no PyObjC version issues)."""
    if sys.platform != "darwin":
        return None
    import ctypes

    try:
        cg = ctypes.CDLL(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        fn = getattr(cg, name)
        fn.restype = ctypes.c_bool
        return bool(fn())
    except Exception:
        return None


def check_permissions(request: bool = False) -> dict:
    """Returns {'screen_recording': bool|None, 'accessibility': bool|None}."""
    out = {"screen_recording": None, "accessibility": None}
    if sys.platform != "darwin":
        return out
    import ctypes

    cg = ctypes.CDLL(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    for key, pre, req in (
        ("screen_recording", "CGPreflightScreenCaptureAccess",
         "CGRequestScreenCaptureAccess"),
        ("accessibility", "CGPreflightPostEventAccess",
         "CGRequestPostEventAccess"),
    ):
        try:
            pre_fn = getattr(cg, pre)
            pre_fn.restype = ctypes.c_bool
            granted = bool(pre_fn())
            if not granted and request:
                req_fn = getattr(cg, req)
                req_fn.restype = ctypes.c_bool
                granted = bool(req_fn())
            out[key] = granted
        except AttributeError:
            out[key] = None
    return out


def open_permission_settings():
    if sys.platform != "darwin":
        return
    subprocess.run(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"],
        capture_output=True,
    )
    subprocess.run(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
        capture_output=True,
    )


# ------------------------------------------------------------------- flow --


def cmd_agents(args):
    rows = agents.detect_all()
    for r in rows:
        mark = "✓" if r["detected"] else " "
        print(f"  [{mark}] {r['id']:<12} {r['name']:<22} ({r['via']})")
    detected = [r for r in rows if r["detected"] and r["id"] != "generic"]
    print(f"\n{len(detected)} agent(s) detected. Install with: scu install")


def _pick_agents(args) -> List[agents.AgentSpec]:
    rows = agents.detect_all()
    detected = [a for a in agents.AGENTS if a.detected() or a.id == "generic"]

    if args.agent:
        if args.agent == "all":
            return detected
        for a in agents.AGENTS:
            if a.id == args.agent:
                return [a]
        print(f"unknown agent {args.agent!r}; known: "
              + ", ".join(a.id for a in agents.AGENTS))
        sys.exit(1)

    print("Agents detected on this machine:")
    for i, a in enumerate(detected):
        tag = "found" if a.detected() else "manual"
        print(f"  {i + 1}. {a.name} ({a.id}) — {a.note} [{tag}]")
    print("  a. all of the above")
    choice = _ask("Install for which agent?", "a")
    if choice.lower() in ("a", "all"):
        return detected
    try:
        return [detected[int(choice) - 1]]
    except (ValueError, IndexError):
        print("invalid choice")
        sys.exit(1)


def _setup_grounding(args) -> None:
    cfg = config.load_config()
    choice = args.grounding

    if choice is None:
        print("\nGrounding setup — how should `scu` turn descriptions like")
        print("'the Save button' into pixels?")
        opts = []
        if grounding.local_supported():
            opts.append(("local", "local UI-TARS-1.5-7B via MLX (recommended, ~5 GB download)"))
        opts.append(("remote", "remote OpenAI-compatible endpoint (HF, vLLM, Parasail...)"))
        opts.append(("none", "skip — use --at coords + OCR text find only"))
        for i, (key, label) in enumerate(opts):
            print(f"  {i + 1}. {label}")
        default = "1" if grounding.local_supported() else "2"
        pick = _ask("Choose", default)
        try:
            choice = opts[int(pick) - 1][0]
        except (ValueError, IndexError):
            choice = "none"

    if choice == "local":
        if not grounding.local_supported():
            print("local grounding requires Apple Silicon macOS; falling back to 'none'")
            cfg["grounding"]["provider"] = "none"
        else:
            if not ensure_mlx_vlm():
                print("mlx-vlm install failed; grounding left unconfigured")
                cfg["grounding"]["provider"] = "none"
            else:
                cfg["grounding"]["provider"] = "local"
                cfg["grounding"].setdefault("local_model", config.DEFAULT_LOCAL_MODEL)
                cfg["grounding"].setdefault("local_port", config.DEFAULT_LOCAL_PORT)
                if _yes(f"Download {config.DEFAULT_LOCAL_MODEL} now?", True,
                        args.yes):
                    download_model(config.DEFAULT_LOCAL_MODEL)

    elif choice == "remote":
        url = _ask("Endpoint URL (OpenAI-compatible)", "http://localhost:8080")
        model = _ask("Model name", "ui-tars-1.5-7b")
        w = _ask("Grounding width (UI-TARS-1.5=1920, UI-TARS-72B=1000)", "1920")
        h = _ask("Grounding height", "1080")
        key = _ask("API key (blank = none)", "")
        cfg["grounding"].update(
            provider="remote", url=url, model=model,
            width=int(w), height=int(h), api_key=key,
        )
    else:
        cfg["grounding"]["provider"] = "none"

    config.save_config(cfg)
    print(f"config written to {config.CONFIG_PATH}")


def cmd_install(args):
    print("simple-computer-use installer\n")

    # 1. deps
    print("[1/4] Dependencies")
    tess = ensure_tesseract(args.yes)
    print(f"  tesseract: {'ok' if tess else 'missing (OCR fallback disabled)'}")

    # 2. grounding
    print("\n[2/4] Grounding model")
    _setup_grounding(args)

    # 3. permissions
    print("\n[3/4] Permissions")
    perms = check_permissions(request=True)
    if sys.platform == "darwin":
        for k, v in perms.items():
            label = "Screen Recording" if k == "screen_recording" else "Accessibility"
            print(f"  {label}: {'granted' if v else 'NOT granted'}")
        if not all(v for v in perms.values()):
            print("\n  Both are required for `scu` to see and drive the screen.")
            print("  Enable them for your terminal app in System Settings, then re-run `scu doctor`.")
            if _yes("Open the settings panes now?", True, args.yes):
                open_permission_settings()
    else:
        print("  (permissions only needed on macOS; on Linux/Windows ensure the")
        print("   process can capture the screen and send input)")

    # 4. agents
    print("\n[4/4] Agent setup")
    chosen = _pick_agents(args)
    for a in chosen:
        try:
            for line in agents.install(a):
                print(f"  {a.name}: {line}")
        except Exception as e:
            print(f"  {a.name}: install failed: {e}")

    print("\nDone. Verify with `scu doctor`, then in your agent ask for a GUI")
    print("task — it will use `scu` commands automatically.")


def cmd_uninstall(args):
    targets = agents.AGENTS
    if args.agent:
        targets = [a for a in agents.AGENTS if a.id == args.agent]
        if not targets:
            print(f"unknown agent {args.agent!r}")
            sys.exit(1)
    for a in targets:
        for line in agents.uninstall(a):
            print(f"  {a.name}: {line}")
    print("Uninstalled. Config/state kept in "
          f"{config.BASE_DIR} (delete manually if unwanted).")
