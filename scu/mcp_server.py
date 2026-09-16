"""Optional MCP stdio server: exposes the `scu` tools over the Model Context
Protocol for agents that prefer tool calls to shell commands (Cursor,
Windsurf, ...).

Requires the `mcp` extra: pip install 'simple-computer-use[mcp]'
"""

import json
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

from scu import actions, screens, state

mcp = FastMCP("simple-computer-use")


def _j(**kw):
    return json.dumps(kw)


@mcp.tool()
def session_start() -> str:
    """Begin a computer-use session: turns on the orange screen glow and the
    agent cursor badge so the user can see the agent working."""
    from scu.cli import glow_start

    state.update(session=True, status="Session started")
    return _j(ok=True, overlay=glow_start())


@mcp.tool()
def session_end() -> str:
    """End the session: removes the glow and badge."""
    from scu.cli import glow_stop

    state.update(session=False)
    glow_stop()
    return _j(ok=True)


@mcp.tool()
def screenshot(screen: Optional[int] = None) -> str:
    """Capture a display and return the PNG file path + display geometry.
    screen=None captures the primary display; call displays() for indices."""
    import datetime
    import os
    from scu import config

    d = screens.get_display(screen)
    png = screens.screenshot(d)
    os.makedirs(config.SHOTS_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(config.SHOTS_DIR, f"screen{d.index}-{ts}.png")
    with open(path, "wb") as f:
        f.write(png)
    state.update(status="Screenshot")
    return _j(path=path, **d.to_dict())


@mcp.tool()
def displays() -> str:
    """List connected displays (index, global bounds, scale, primary)."""
    return _j(displays=[d.to_dict() for d in screens.displays()])


@mcp.tool()
def ground(desc: str, screen: Optional[int] = None) -> str:
    """Resolve an element description to global coordinates (needs a
    configured grounding model)."""
    from scu import grounding

    d = screens.get_display(screen)
    fx, fy, raw = grounding.ground(desc, screens.screenshot(d))
    x, y = screens.fraction_to_point(fx, fy, d)
    state.update(status=f"Grounded '{desc}'", screen=d.display_id)
    return _j(x=x, y=y, screen=d.index, raw=raw)


@mcp.tool()
def click(desc: Optional[str] = None, x: Optional[int] = None,
          y: Optional[int] = None, screen: Optional[int] = None,
          clicks: int = 1, button: str = "left") -> str:
    """Click an element by description, or at explicit global x,y."""
    at = (x, y) if x is not None and y is not None else None
    r = actions.click(desc=desc, at=at, screen=screen, num_clicks=clicks,
                      button=button)
    return _j(**r)


@mcp.tool()
def type_text(text: str, into: Optional[str] = None, x: Optional[int] = None,
              y: Optional[int] = None, screen: Optional[int] = None,
              overwrite: bool = False, enter: bool = False) -> str:
    """Type text; optionally click an element first. Unicode-safe."""
    at = (x, y) if x is not None and y is not None else None
    r = actions.type_text(text, into=into, at=at, screen=screen,
                          overwrite=overwrite, enter=enter)
    return _j(**r)


@mcp.tool()
def scroll(clicks: int, on: Optional[str] = None, x: Optional[int] = None,
           y: Optional[int] = None, screen: Optional[int] = None,
           horizontal: bool = False) -> str:
    """Scroll; +clicks up / -clicks down, or horizontal."""
    at = (x, y) if x is not None and y is not None else None
    r = actions.scroll(clicks, on=on, at=at, screen=screen,
                       horizontal=horizontal)
    return _j(**r)


@mcp.tool()
def drag(from_desc: Optional[str] = None, to_desc: Optional[str] = None,
         from_x: Optional[int] = None, from_y: Optional[int] = None,
         to_x: Optional[int] = None, to_y: Optional[int] = None,
         screen: Optional[int] = None) -> str:
    """Drag between two elements or coordinates."""
    fa = (from_x, from_y) if from_x is not None else None
    ta = (to_x, to_y) if to_x is not None else None
    return _j(**actions.drag(from_desc, to_desc, fa, ta, screen))


@mcp.tool()
def hotkey(keys: List[str]) -> str:
    """Press a key combination, e.g. ["cmd","shift","s"]."""
    return _j(**actions.hotkey(keys))


@mcp.tool()
def open_app(name: str) -> str:
    """Open or focus an application by name."""
    return _j(**actions.open_app(name))


@mcp.tool()
def find_text(phrase: str, screen: Optional[int] = None) -> str:
    """Find on-screen text via OCR; returns candidate coordinates."""
    from scu import ocr

    d = screens.get_display(screen)
    ms = ocr.find(phrase, screens.screenshot(d))
    for m in ms:
        m["x"], m["y"] = screens.fraction_to_point(m["fx"], m["fy"], d)
        m["screen"] = d.index
    state.update(status=f"Find text '{phrase}'")
    return _j(matches=ms)


@mcp.tool()
def set_status(message: str) -> str:
    """Set the cursor badge text shown to the user."""
    state.update(status=message)
    return _j(ok=True)


def run():
    mcp.run()
