"""Shared state between the CLI tools and the overlay daemon.

State file: ~/.config/simple-computer-use/state.json

    {
      "session": true,                  # a computer-use session is active
      "status": "Clicking 'Save'",      # text shown in the cursor badge
      "screens": {"<display_id>": true},# displays currently being worked on
      "updated": 1690000000.0           # last write timestamp
    }

Every tool writes here so the overlay (orange glow + cursor badge) can render
what the agent is doing without the tools and the UI sharing a process.
"""

import json
import os
import time
from typing import Any, Dict, Optional

from scu.config import STATE_PATH, ensure_dirs


def read() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"session": False, "status": "", "screens": {}, "updated": 0.0}


def write(state: Dict[str, Any]) -> None:
    ensure_dirs()
    state["updated"] = time.time()
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH)


def update(
    status: Optional[str] = None,
    screen: Optional[Any] = None,
    session: Optional[bool] = None,
) -> Dict[str, Any]:
    """Merge an update into the state file.

    status  — text for the cursor badge (None keeps current, "" clears)
    screen  — display id/index the agent just acted on (marks it active)
    session — explicitly open/close a session
    """
    st = read()
    if session is not None:
        st["session"] = bool(session)
        if not session:
            st["status"] = ""
            st["screens"] = {}
    if status is not None:
        st["status"] = status
    if screen is not None:
        st.setdefault("screens", {})[str(screen)] = True
    write(st)
    return st


def session_active() -> bool:
    return bool(read().get("session"))
