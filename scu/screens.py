"""Display enumeration and per-display screenshots.

Coordinates are in GLOBAL SCREEN POINTS, origin at the top-left corner of the
primary display — the same space pyautogui uses for mouse events on macOS,
Linux and Windows. Screenshots are captured per display at native (pixel)
resolution; callers map between the two spaces with fraction_to_point().

macOS uses Quartz (CGWindowListCreateImage) so every attached display can be
captured and acted on independently. Other platforms fall back to a single
virtual display covering pyautogui's screenshot.
"""

import io
import subprocess
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

import pyautogui
from PIL import Image

IS_DARWIN = sys.platform == "darwin"

try:
    import Quartz  # pyobjc-framework-Quartz

    _HAS_QUARTZ = True
except ImportError:
    _HAS_QUARTZ = False


@dataclass
class Display:
    index: int  # position in displays()
    display_id: int  # CGDirectDisplayID on macOS, index elsewhere
    x: int  # global-space origin (points)
    y: int
    w: int  # size in points
    h: int
    scale: float  # pixels per point (2.0 = retina)
    primary: bool

    def to_dict(self):
        return asdict(self)

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


def _darwin_displays() -> List[Display]:
    err, ids, count = Quartz.CGGetActiveDisplayList(32, None, None)
    main_id = Quartz.CGMainDisplayID()
    out = []
    for i in range(count):
        did = ids[i]
        b = Quartz.CGDisplayBounds(did)
        px_w = Quartz.CGDisplayPixelsWide(did)
        scale = px_w / b.size.width if b.size.width else 1.0
        out.append(
            Display(
                index=i,
                display_id=int(did),
                x=int(b.origin.x),
                y=int(b.origin.y),
                w=int(b.size.width),
                h=int(b.size.height),
                scale=scale,
                primary=(did == main_id),
            )
        )
    return out


def _fallback_displays() -> List[Display]:
    w, h = pyautogui.size()
    return [
        Display(
            index=0,
            display_id=0,
            x=0,
            y=0,
            w=int(w),
            h=int(h),
            scale=1.0,
            primary=True,
        )
    ]


def displays() -> List[Display]:
    if IS_DARWIN and _HAS_QUARTZ:
        try:
            ds = _darwin_displays()
            if ds:
                return ds
        except Exception:
            pass
    return _fallback_displays()


def get_display(screen=None) -> Display:
    """Resolve a --screen argument (None -> primary, else index)."""
    ds = displays()
    if screen is None:
        for d in ds:
            if d.primary:
                return d
        return ds[0]
    for d in ds:
        if d.index == int(screen):
            return d
    raise ValueError(
        f"screen {screen} not found; have {len(ds)} display(s): "
        + ", ".join(str(d.index) for d in ds)
    )


def display_for_point(x: float, y: float) -> Optional[Display]:
    for d in displays():
        if d.contains(x, y):
            return d
    return None


def _cgimage_to_png(image) -> bytes:
    data = Quartz.CFMutableDataCreate(None, 0)
    dest = Quartz.CGImageDestinationCreateWithData(data, "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(dest, image, None)
    if not Quartz.CGImageDestinationFinalize(dest):
        raise RuntimeError("CGImageDestinationFinalize failed")
    return bytes(data)


def _darwin_screenshot(disp: Display) -> bytes:
    rect = Quartz.CGRectMake(disp.x, disp.y, disp.w, disp.h)
    image = Quartz.CGWindowListCreateImage(
        rect,
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageBestResolution,
    )
    if image is None:
        raise RuntimeError(
            "screenshot failed — is Screen Recording permission granted?"
        )
    return _cgimage_to_png(image)


def _screencapture_screenshot(disp: Display, path: str) -> bytes:
    # `screencapture -D n` uses 1-based display index in CG order.
    subprocess.run(
        ["screencapture", "-x", "-D", str(disp.index + 1), path],
        check=True,
        capture_output=True,
    )
    with open(path, "rb") as f:
        return f.read()


def screenshot(disp: Display) -> bytes:
    """PNG bytes for one display at native resolution."""
    if IS_DARWIN:
        if _HAS_QUARTZ:
            try:
                return _darwin_screenshot(disp)
            except Exception:
                pass
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
            return _screencapture_screenshot(disp, t.name)

    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def fraction_to_point(fx: float, fy: float, disp: Display) -> Tuple[int, int]:
    """0-1 position inside a display's screenshot -> global point."""
    return (
        int(round(disp.x + fx * disp.w)),
        int(round(disp.y + fy * disp.h)),
    )


def point_to_fraction(x: float, y: float, disp: Display) -> Tuple[float, float]:
    return ((x - disp.x) / disp.w, (y - disp.y) / disp.h)


def open_image(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes))
