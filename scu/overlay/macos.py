"""macOS overlay: orange glow around active displays + agent cursor badge.

Runs inside `python -m scu.overlay.daemon`. One borderless, click-through,
above-everything window per NSScreen draws the glow; a second small window
follows the pointer and shows the agent's current action label, Codex-style.

The daemon polls ~/.config/simple-computer-use/state.json; tools write to it
on every action, so the UI tracks the agent with no IPC beyond a file.
"""

import time

import AppKit
import Foundation
import Quartz
import objc

from scu import state

ORANGE = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_
ACCENT = (1.0, 0.55, 0.0)
BADGE_OFFSET = (14.0, -40.0)  # relative to pointer, AppKit bottom-left coords
IDLE_TIMEOUT_S = 600  # exit if no tool has updated state for 10 minutes


class GlowView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(GlowView, self).initWithFrame_(frame)
        if self is not None:
            self.active = False
        return self

    def drawRect_(self, rect):
        bounds = self.bounds()
        AppKit.NSColor.clearColor().set()
        AppKit.NSRectFill(bounds)

        inset = 8.0
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            AppKit.NSMakeRect(
                inset, inset, bounds.size.width - 2 * inset,
                bounds.size.height - 2 * inset,
            ),
            12.0,
            12.0,
        )
        ctx = AppKit.NSGraphicsContext.currentContext()
        ctx.saveGraphicsState()
        if self.active:
            glow = ORANGE(ACCENT[0], ACCENT[1], ACCENT[2], 0.9)
            shadow = AppKit.NSShadow.alloc().init()
            shadow.setShadowColor_(glow)
            shadow.setShadowBlurRadius_(24.0)
            shadow.set()
            ORANGE(*ACCENT, 0.95).setStroke()
            path.setLineWidth_(5.0)
        else:
            ORANGE(*ACCENT, 0.18).setStroke()
            path.setLineWidth_(3.0)
        path.stroke()
        ctx.restoreGraphicsState()


class BadgeView(AppKit.NSView):
    def initWithFrame_(self, frame):
        self = objc.super(BadgeView, self).initWithFrame_(frame)
        if self is not None:
            self.text = ""
        return self

    def drawRect_(self, rect):
        AppKit.NSColor.clearColor().set()
        AppKit.NSRectFill(self.bounds())
        b = self.bounds()

        # ring marking the agent's pointer position (left edge of the badge)
        ring = AppKit.NSBezierPath.bezierPathWithOvalInRect_(
            AppKit.NSMakeRect(4, b.size.height / 2 - 6, 12, 12)
        )
        ORANGE(*ACCENT, 1.0).setStroke()
        ring.setLineWidth_(2.5)
        ring.stroke()

        # status pill
        pill = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            AppKit.NSMakeRect(22, 4, b.size.width - 26, b.size.height - 8),
            (b.size.height - 8) / 2,
            (b.size.height - 8) / 2,
        )
        AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.08, 0.72).setFill()
        pill.fill()
        ORANGE(*ACCENT, 0.85).setStroke()
        pill.setLineWidth_(1.2)
        pill.stroke()

        if self.text:
            attrs = {
                AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_weight_(
                    12.5, AppKit.NSFontWeightMedium
                ),
                AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor(),
            }
            s = AppKit.NSString.stringWithString_(self.text)
            size = s.sizeWithAttributes_(attrs)
            s.drawAtPoint_withAttributes_(
                Foundation.NSMakePoint(32, (b.size.height - size.height) / 2),
                attrs,
            )


def _borderless_window(frame, level):
    w = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame,
        AppKit.NSWindowStyleMaskBorderless,
        AppKit.NSBackingStoreBuffered,
        False,
    )
    w.setLevel_(level)
    w.setOpaque_(False)
    w.setBackgroundColor_(AppKit.NSColor.clearColor())
    w.setIgnoresMouseEvents_(True)
    w.setHasShadow_(False)
    w.setCollectionBehavior_(
        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
        | AppKit.NSWindowCollectionBehaviorStationary
        | AppKit.NSWindowCollectionBehaviorIgnoresCycle
    )
    return w


class OverlayController(AppKit.NSObject):
    def init(self):
        self = objc.super(OverlayController, self).init()
        if self is None:
            return None
        self.glow_windows = {}  # display_id -> (NSWindow, GlowView)
        self.badge = None
        self.badge_view = None
        return self

    def _screen_id(self, screen):
        desc = screen.deviceDescription()
        return int(desc.get("NSScreenNumber", 0))

    def _sync_glow_windows(self, active_ids):
        screens = AppKit.NSScreen.screens()
        want = {self._screen_id(s): s for s in screens}

        for did in list(self.glow_windows):
            if did not in want:
                win, _ = self.glow_windows.pop(did)
                win.orderOut_(None)

        for did, screen in want.items():
            if did not in self.glow_windows:
                win = _borderless_window(
                    screen.frame(), AppKit.NSScreenSaverWindowLevel
                )
                view = GlowView.alloc().initWithFrame_(
                    AppKit.NSMakeRect(
                        0, 0, screen.frame().size.width,
                        screen.frame().size.height,
                    )
                )
                win.setContentView_(view)
                win.orderFrontRegardless()
                self.glow_windows[did] = (win, view)
            win, view = self.glow_windows[did]
            if win.frame() != screen.frame():
                win.setFrame_display_(screen.frame(), True)
            active = (not active_ids) or (str(did) in active_ids)
            if view.active != active:
                view.active = active
                view.setNeedsDisplay_(True)

    def _sync_badge(self, text):
        if self.badge is None:
            self.badge_view = BadgeView.alloc().initWithFrame_(
                AppKit.NSMakeRect(0, 0, 300, 30)
            )
            self.badge = _borderless_window(
                AppKit.NSMakeRect(0, 0, 300, 30),
                AppKit.NSScreenSaverWindowLevel + 1,
            )
            self.badge.setContentView_(self.badge_view)
        if not text:
            self.badge.orderOut_(None)
            return

        attrs = {
            AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_weight_(
                12.5, AppKit.NSFontWeightMedium
            )
        }
        s = AppKit.NSString.stringWithString_(text)
        tw = s.sizeWithAttributes_(attrs).width
        w = min(max(tw + 46, 90), 560)
        h = 30.0

        mouse = AppKit.NSEvent.mouseLocation()
        origin = Foundation.NSMakePoint(
            mouse.x + BADGE_OFFSET[0], mouse.y + BADGE_OFFSET[1]
        )
        frame = AppKit.NSMakeRect(origin.x, origin.y, w, h)

        # keep the badge on whatever display the pointer is on
        for screen in AppKit.NSScreen.screens():
            sf = screen.frame()
            if AppKit.NSPointInRect(mouse, sf):
                if frame.origin.x + w > sf.origin.x + sf.size.width:
                    frame.origin.x = mouse.x - w - BADGE_OFFSET[0]
                if frame.origin.y < sf.origin.y:
                    frame.origin.y = mouse.y + 26
                break

        if self.badge_view.text != text:
            self.badge_view.text = text
            self.badge_view.setFrameSize_(Foundation.NSMakeSize(w, h))
            self.badge_view.setNeedsDisplay_(True)
        self.badge.setFrame_display_(frame, False)
        self.badge.orderFrontRegardless()

    def tick_(self, timer):
        st = state.read()
        # Exit when the session ends OR the agent went away without ending it
        # (no state writes for IDLE_TIMEOUT_S — every action updates it).
        if not st.get("session") or (
            time.time() - st.get("updated", 0) > IDLE_TIMEOUT_S
        ):
            state.update(session=False)
            AppKit.NSApplication.sharedApplication().terminate_(None)
            return
        self._sync_glow_windows(st.get("screens") or {})
        self._sync_badge(st.get("status") or "")


def run():
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    controller = OverlayController.alloc().init()
    AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        0.08, controller, objc.selector(controller.tick_, signature=b"v@:@"), None, True
    )
    app.run()
