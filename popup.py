#!/usr/bin/env python3
"""The little translation popup — right edge, vertically centred, auto-dismissing.

One persistent Toplevel that is re-filled for every translation, so a new hotkey press while
a result is still on screen replaces it instead of stacking a second window.

Borderless and non-focus-stealing via X11 override-redirect (through XWayland), the same
technique local-wisprflow's listening pill uses — you can keep typing while it appears.

Standalone demo:  python3 popup.py
"""
import time
import tkinter as tk

from theme import (ACCENT, ACCENT2, BG, BORDER, CARD, CARD_HI, FG, FPS, OKC, REC, SUBTLE,
                   Theme, apply_ttk_style, round_rect)

MAX_BODY_CHARS = 1200          # displayed; the full text still goes to clipboard + history


class TranslationPopup:
    def __init__(self, root: tk.Tk, th: Theme, cfg: dict):
        self.root, self.th, self.cfg = root, th, cfg
        w = tk.Toplevel(root)
        w.withdraw()               # stay hidden until fully configured -> never flash
        w.overrideredirect(True)   # borderless AND never takes focus
        w.attributes("-topmost", True)
        try:
            w.attributes("-alpha", 0.98)
        except tk.TclError:
            pass
        w.configure(bg=BG)
        self.win = w
        self.cv = tk.Canvas(w, bg=BG, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Button-1>", lambda _e: self.hide())
        self.cv.bind("<Enter>", self._on_enter)
        self.cv.bind("<Leave>", self._on_leave)
        self._hide_after = None
        self._spin_after = None
        self._hoverable = False

    # -- timers ---------------------------------------------------------------
    def _cancel_hide(self):
        if self._hide_after is not None:
            try:
                self.root.after_cancel(self._hide_after)
            except Exception:  # noqa: BLE001
                pass
            self._hide_after = None

    def _arm_hide(self, seconds: float):
        self._cancel_hide()
        self._hide_after = self.root.after(int(seconds * 1000), self.hide)

    def _stop_spin(self):
        if self._spin_after is not None:
            try:
                self.root.after_cancel(self._spin_after)
            except Exception:  # noqa: BLE001
                pass
            self._spin_after = None

    def _on_enter(self, _e):
        # Hovering pauses the countdown so a long translation can actually be read.
        if self._hoverable:
            self._cancel_hide()

    def _on_leave(self, _e):
        if self._hoverable:
            self._arm_hide(1.5)

    # -- geometry -------------------------------------------------------------
    def _place(self, w: int, h: int):
        th = self.th
        th.refresh_monitor()       # monitor layout can change mid-session
        x = th.OX + th.MW - w - th.S(24)
        y = th.OY + (th.MH - h) // 2
        self.cv.configure(width=w, height=h)
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _card(self, w: int, h: int):
        S = self.th.S
        pad, r, lw = S(2), S(14), max(1, self.th.S(1))
        round_rect(self.cv, pad, pad, w - pad, h - pad, r,
                   fill=CARD, outline=BORDER, width=lw)
        self.cv.create_line(pad + r, pad + lw, w - pad - r, pad + lw, fill=CARD_HI, width=lw)

    def _measure(self, text: str, wrap: int, font) -> int:
        probe = self.cv.create_text(0, 0, text=text, anchor="nw", width=wrap, font=font)
        bb = self.cv.bbox(probe)
        self.cv.delete(probe)
        return (bb[3] - bb[1]) if bb else 0

    def _show(self):
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)   # re-assert; some WMs drop it across withdraw

    # -- states ---------------------------------------------------------------
    def show_busy(self, label: str = "Translating…"):
        """Spinner while the model works (covers the 5-15s cold start after keep_alive expiry)."""
        S, th = self.th.S, self.th
        self._stop_spin()
        self._cancel_hide()
        self._hoverable = False
        self.cv.delete("all")
        w, h = S(250), S(64)
        self._place(w, h)
        self._card(w, h)
        cx, cy, rr = S(32), h // 2, S(11)
        self.cv.create_text(S(56), cy, text=label, anchor="w", fill=FG, font=th.F_TITLE)
        t0 = time.time()

        def spin():
            self.cv.delete("spin")
            ang = (time.time() - t0) * 320.0 % 360
            self.cv.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=ang, extent=270,
                               style="arc", outline=ACCENT, width=max(2, S(2)), tags="spin")
            self._spin_after = self.root.after(int(1000 / FPS), spin)

        spin()
        self._show()
        # Safety net: never leave a spinner on screen if a worker somehow never reports back.
        self._hide_after = self.root.after(
            int((self.cfg["llm_timeout"] + 10) * 1000), self.hide)

    def show_result(self, entry: dict, auto_copied: bool):
        S, th = self.th.S, self.th
        header = f"{entry['source_language']}  →  {entry['target_language']}"
        if entry.get("truncated"):
            header += "  ·  truncated"
        body = entry["translation"]
        if len(body) > MAX_BODY_CHARS:
            body = body[:MAX_BODY_CHARS].rstrip() + "…"
            if auto_copied:
                body += "\n(full text copied to clipboard)"
        self._render(header, ACCENT2, body, FG,
                     badge=("✓ copied" if auto_copied else None))
        self._arm_hide(self.cfg["popup_seconds"])

    def show_error(self, message: str):
        self._render("⚠  Sinlate", REC, message, SUBTLE, badge=None)
        self._arm_hide(3.5)

    def _render(self, header: str, header_color: str, body: str, body_color: str, badge):
        S, th = self.th.S, self.th
        self._stop_spin()
        self._cancel_hide()
        self.cv.delete("all")
        th.refresh_monitor()

        w = S(380)
        pad = S(15)
        wrap = w - 2 * pad
        head_y = pad
        body_y = pad + S(22)
        max_h = int(th.MH * 0.6)

        # Shrink the displayed text until the card fits the height budget (bounded loop).
        body_h = self._measure(body, wrap, th.F_BODY)
        while body_y + body_h + pad > max_h and len(body) > 200:
            body = body[:int(len(body) * 0.8)].rstrip() + "…"
            body_h = self._measure(body, wrap, th.F_BODY)

        h = max(S(64), min(max_h, body_y + body_h + pad))
        self._place(w, h)
        self._card(w, h)

        self.cv.create_text(pad, head_y, text=header, anchor="nw",
                            fill=header_color, font=th.F_SUB)
        if badge:
            self.cv.create_text(w - pad, head_y, text=badge, anchor="ne",
                                fill=OKC, font=th.F_SUB)
        self.cv.create_text(pad, body_y, text=body, anchor="nw", width=wrap,
                            fill=body_color, font=th.F_BODY)
        self._hoverable = True
        self._show()

    def hide(self):
        self._stop_spin()
        self._cancel_hide()
        self._hoverable = False
        self.win.withdraw()


if __name__ == "__main__":
    from config import load_config

    root = tk.Tk()
    root.withdraw()
    th = Theme(root)
    apply_ttk_style(root, th)
    cfg = load_config()
    p = TranslationPopup(root, th, cfg)

    demo = [
        (0, lambda: p.show_busy()),
        (2500, lambda: p.show_result(
            {"source_language": "German", "target_language": "English",
             "translation": "Where is the train station? I missed my train and the next one "
                            "does not leave for another hour, so I will be late.",
             "truncated": False}, True)),
        (9000, lambda: p.show_error("Translation engine offline.\n"
                                    "Start it:  systemctl --user start wf-cleanup-llm.service")),
        (14000, root.destroy),
    ]
    for ms, fn in demo:
        root.after(ms, fn)
    print("popup demo: spinner -> result -> error, then exits (~14s)")
    root.mainloop()
