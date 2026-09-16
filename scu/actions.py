"""Computer-use actions: semantic in, executed on the host GUI.

Each function performs the action immediately via pyautogui and reports what
it did to the overlay state file (status text + which display was used), so
the orange glow / cursor badge follows the agent live.

Target resolution order for click/type/scroll/drag:
  1. --at x y          explicit global-point coordinates
  2. grounding model   natural-language description -> UI-TARS point
  3. OCR find-text     if grounding is unconfigured and the description
                       matches on-screen text
"""

import platform
import subprocess
import sys
import time
from typing import List, Optional, Tuple

import pyautogui
import pyperclip

from scu import grounding, ocr, screens, state

IS_DARWIN = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
MOD_KEY = "command" if IS_DARWIN else "ctrl"


class ActionError(RuntimeError):
    pass


def _status(msg: str, display=None) -> None:
    try:
        state.update(status=msg, screen=display.display_id if display else None)
    except Exception:
        pass  # overlay state must never break an action


def resolve_point(
    desc: Optional[str] = None,
    at: Optional[Tuple[float, float]] = None,
    screen: Optional[int] = None,
) -> Tuple[int, int, screens.Display, dict]:
    """Resolve a target to global point coords.

    Returns (x, y, display, info) where info carries provenance
    ({"via": "grounding"|"at"|"ocr", ...}).
    """
    ds = screens.displays()

    if at is not None:
        x, y = int(at[0]), int(at[1])
        disp = screens.display_for_point(x, y) or screens.get_display(screen)
        return x, y, disp, {"via": "at", "x": x, "y": y}

    if not desc:
        raise ActionError("need a description or --at x y")

    disp = screens.get_display(screen)
    shot = screens.screenshot(disp)

    # 1) grounding model
    try:
        fx, fy, raw = grounding.ground(desc, shot)
        x, y = screens.fraction_to_point(fx, fy, disp)
        return x, y, disp, {"via": "grounding", "raw": raw, "fx": fx, "fy": fy}
    except grounding.GroundingError:
        pass

    # 2) OCR text match — descriptions of literal on-screen text still work
    #    with no grounding model configured.
    try:
        matches = ocr.find(desc, shot, limit=1)
    except Exception:
        matches = []
    if matches and matches[0]["score"] >= 0.8:
        m = matches[0]
        x, y = screens.fraction_to_point(m["fx"], m["fy"], disp)
        return x, y, disp, {"via": "ocr", "matched": m["text"], "score": m["score"]}

    raise ActionError(
        f"could not locate {desc!r}: no grounding model configured and OCR "
        "found no matching text. Use `scu screenshot` + `--at x y`, or run "
        "`scu install` to set up grounding."
    )


def click(
    desc: Optional[str] = None,
    at: Optional[Tuple[float, float]] = None,
    screen: Optional[int] = None,
    num_clicks: int = 1,
    button: str = "left",
    hold: Optional[List[str]] = None,
) -> dict:
    x, y, disp, info = resolve_point(desc, at, screen)
    label = desc or f"{x},{y}"
    _status(f"Clicking '{label}'", disp)
    hold = hold or []
    for k in hold:
        pyautogui.keyDown(k)
    try:
        pyautogui.click(x, y, clicks=num_clicks, button=button)
    finally:
        for k in hold:
            pyautogui.keyUp(k)
    return {
        "action": "click",
        "x": x,
        "y": y,
        "screen": disp.index,
        "clicks": num_clicks,
        "button": button,
        **info,
    }


def type_text(
    text: str,
    into: Optional[str] = None,
    at: Optional[Tuple[float, float]] = None,
    screen: Optional[int] = None,
    overwrite: bool = False,
    enter: bool = False,
) -> dict:
    info = {"via": "none"}
    disp = screens.get_display(screen)
    if into or at:
        x, y, disp, info = resolve_point(into, at, screen)
        _status(f"Typing into '{into or f'{x},{y}'}'", disp)
        pyautogui.click(x, y)
        time.sleep(0.2)
    else:
        _status("Typing", disp)

    if overwrite:
        pyautogui.hotkey(MOD_KEY, "a")
        pyautogui.press("backspace")

    has_unicode = any(ord(c) > 127 for c in text)
    if has_unicode:
        pyperclip.copy(text)
        pyautogui.hotkey(MOD_KEY, "v")
    else:
        pyautogui.write(text, interval=0.01)
    if enter:
        pyautogui.press("enter")
    return {
        "action": "type",
        "chars": len(text),
        "unicode": has_unicode,
        "screen": disp.index,
        **info,
    }


def scroll(
    clicks: int,
    on: Optional[str] = None,
    at: Optional[Tuple[float, float]] = None,
    screen: Optional[int] = None,
    horizontal: bool = False,
) -> dict:
    info = {"via": "none"}
    disp = screens.get_display(screen)
    if on or at:
        x, y, disp, info = resolve_point(on, at, screen)
        pyautogui.moveTo(x, y)
        time.sleep(0.3)
        _status(f"Scrolling on '{on or f'{x},{y}'}'", disp)
    else:
        _status("Scrolling", disp)

    if horizontal:
        try:
            pyautogui.hscroll(clicks)
        except (AttributeError, NotImplementedError):
            pyautogui.keyDown("shift")
            pyautogui.scroll(clicks)
            pyautogui.keyUp("shift")
    else:
        pyautogui.scroll(clicks)
    return {
        "action": "scroll",
        "clicks": clicks,
        "horizontal": horizontal,
        "screen": disp.index,
        **info,
    }


def drag(
    from_desc: Optional[str] = None,
    to_desc: Optional[str] = None,
    from_at: Optional[Tuple[float, float]] = None,
    to_at: Optional[Tuple[float, float]] = None,
    screen: Optional[int] = None,
    hold: Optional[List[str]] = None,
    duration: float = 1.0,
) -> dict:
    x1, y1, d1, i1 = resolve_point(from_desc, from_at, screen)
    x2, y2, d2, i2 = resolve_point(to_desc, to_at, screen)
    _status(f"Dragging '{from_desc or f'{x1},{y1}'}' -> '{to_desc or f'{x2},{y2}'}'", d1)
    hold = hold or []
    pyautogui.moveTo(x1, y1)
    for k in hold:
        pyautogui.keyDown(k)
    try:
        pyautogui.dragTo(x2, y2, duration=duration, button="left")
        pyautogui.mouseUp()
    finally:
        for k in hold:
            pyautogui.keyUp(k)
    return {
        "action": "drag",
        "from": {"x": x1, "y": y1, **i1},
        "to": {"x": x2, "y": y2, **i2},
        "screen": d1.index,
    }


def hotkey(keys: List[str]) -> dict:
    _status("Hotkey " + "+".join(keys))
    pyautogui.hotkey(*keys)
    return {"action": "hotkey", "keys": keys}


def press(key: str, presses: int = 1) -> dict:
    _status(f"Press {key}")
    pyautogui.press(key, presses=presses)
    return {"action": "press", "key": key, "presses": presses}


def open_app(name: str) -> dict:
    """Open/focus an application by name."""
    _status(f"Opening '{name}'")
    if IS_DARWIN:
        r = subprocess.run(["open", "-a", name], capture_output=True, text=True)
        if r.returncode != 0:
            # Fall back to Spotlight-style launch for files/non-app names.
            pyautogui.hotkey("command", "space", interval=0.5)
            time.sleep(0.5)
            pyautogui.write(name)
            time.sleep(0.5)
            pyautogui.press("enter")
    elif IS_WINDOWS:
        pyautogui.hotkey("win")
        time.sleep(0.5)
        pyautogui.write(name)
        time.sleep(0.8)
        pyautogui.press("enter")
    else:
        pyautogui.hotkey("win")
        time.sleep(0.5)
        pyautogui.write(name)
        time.sleep(0.8)
        pyautogui.hotkey("enter")
    time.sleep(1.0)
    return {"action": "open", "name": name}


def focus_app(name: str) -> dict:
    """Bring an already-open application to the front."""
    _status(f"Focusing '{name}'")
    if IS_DARWIN:
        subprocess.run(["open", "-a", name], capture_output=True)
    elif IS_WINDOWS:
        # Best effort: alt-tab style via launch shortcut is unreliable;
        # ask the shell to activate by window title.
        subprocess.run(
            [
                "powershell",
                "-Command",
                f"(New-Object -ComObject WScript.Shell).AppActivate('{name}')",
            ],
            capture_output=True,
        )
    else:
        subprocess.run(["wmctrl", "-a", name], capture_output=True)
    time.sleep(0.8)
    return {"action": "focus", "name": name}


def wait(seconds: float) -> dict:
    time.sleep(seconds)
    return {"action": "wait", "seconds": seconds}
