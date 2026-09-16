"""Generic overlay fallback (Linux/Windows) using tkinter.

Orange border window per display + a status badge that follows the pointer.
Less polished than the macOS path but functionally equivalent.
"""

import sys
import time
import tkinter as tk

from scu import state

ORANGE = "#ff8c00"
IDLE_TIMEOUT_S = 600  # exit if no tool has updated state for 10 minutes


def run():
    root = tk.Tk()
    root.withdraw()

    glows = []
    badge = tk.Toplevel(root)
    badge.overrideredirect(True)
    badge.attributes("-topmost", True)
    badge_lbl = tk.Label(
        badge,
        text="",
        bg="#1a1a1a",
        fg="white",
        font=("Helvetica", 11),
        padx=10,
        pady=4,
        highlightbackground=ORANGE,
        highlightthickness=1,
    )
    badge_lbl.pack()
    badge.withdraw()

    def make_glow():
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.9)
        except tk.TclError:
            pass
        canvas = tk.Canvas(win, highlightthickness=0, bg="black")
        canvas.pack(fill="both", expand=True)
        # try to make the interior transparent (X11 compositor / Windows)
        try:
            win.wm_attributes("-transparent", True)
            canvas.configure(bg="systemTransparent")
        except tk.TclError:
            try:
                win.wm_attributes("-transparentcolor", "black")
            except tk.TclError:
                pass
        return win, canvas

    def tick():
        st = state.read()
        if not st.get("session") or (
            time.time() - st.get("updated", 0) > IDLE_TIMEOUT_S
        ):
            state.update(session=False)
            root.destroy()
            return

        # one glow window per display (tk reports virtual size)
        n = max(1, len(glows) or 1)
        if not glows:
            w = root.winfo_screenwidth()
            h = root.winfo_screenheight()
            win, canvas = make_glow()
            win.geometry(f"{w}x{h}+0+0")
            glows.append((win, canvas))
        active = bool((st.get("screens") or {})) or st.get("session")
        for win, canvas in glows:
            w, h = win.winfo_width(), win.winfo_height()
            canvas.delete("all")
            lw = 6 if active else 3
            canvas.create_rectangle(
                8, 8, w - 8, h - 8, outline=ORANGE, width=lw
            )

        text = st.get("status") or ""
        if text:
            badge_lbl.configure(text=text)
            px, py = root.winfo_pointerxy()
            badge.geometry(f"+{px + 16}+{py + 18}")
            badge.deiconify()
        else:
            badge.withdraw()
        root.after(80, tick)

    root.after(80, tick)
    root.mainloop()
