#!/usr/bin/env python3
"""Sinlate look & feel — dark glassy palette, DPI scaling, monitor geometry, ttk restyling.

Palette and the DPI/monitor logic are lifted from local-wisprflow's wf-overlay.py so both
tools read as one family on this Win7-Aero-themed desktop.

Why scale from DPI and not from winfo_screenwidth(): tkinter reports the whole VIRTUAL
desktop width across all monitors, which explodes the scale factor on multi-monitor setups
and would place windows across a monitor seam.
"""
import re
import subprocess
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# ---- palette (dark, glassy — sits with the desktop's Win7-Aero theme) --------------------
BG      = "#0c0d11"    # window backdrop
CARD    = "#191c24"    # card / popup body
CARD_HI = "#262a35"    # top bevel highlight
BORDER  = "#39415a"
ACCENT  = "#5b93ff"    # brand blue
ACCENT2 = "#93b8ff"    # secondary accent (language header)
OKC     = "#3ddc84"    # success / copied
REC     = "#ff5c5c"    # error
FG      = "#f2f4f9"
SUBTLE  = "#96a0b4"
BTN     = "#242835"
BTN_HOV = "#2e3342"
BTN_BRD = "#404862"

FPS = 30


def primary_monitor(fallback):
    """(w, h, x, y) of the primary monitor from xrandr; falls back to the whole screen."""
    try:
        out = subprocess.check_output(["xrandr", "--query"], text=True, timeout=2)
    except Exception:  # noqa: BLE001
        return fallback
    first = None
    for line in out.splitlines():
        if " connected" not in line:
            continue
        m = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", line)
        if not m:
            continue
        rect = tuple(int(v) for v in m.groups())
        if " connected primary" in line:
            return rect
        if first is None:
            first = rect
    return first or fallback


def pick_family(root) -> str:
    try:
        fams = set(tkfont.families(root))
    except Exception:  # noqa: BLE001
        return "Sans"
    for f in ("Inter", "Cantarell", "Ubuntu", "Segoe UI", "Noto Sans", "DejaVu Sans", "Sans"):
        if f in fams:
            return f
    return "Sans"


def round_rect(c, x1, y1, x2, y2, r, **kw):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class Theme:
    """Scale factor, fonts and monitor geometry — built once, after the Tk root exists."""

    def __init__(self, root: tk.Tk):
        self.root = root
        try:
            dpi_scale = root.winfo_fpixels("1i") / 96.0
        except Exception:  # noqa: BLE001
            dpi_scale = 1.0

        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        # Fallback assumes ONE monitor no wider than 16:10 of its height, so that without
        # xrandr we still never place a window across a multi-monitor seam.
        self.MW, self.MH, self.OX, self.OY = primary_monitor(
            (min(sw, int(sh * 16 / 10)), sh, 0, 0))

        scale = dpi_scale
        if scale < 1.05:            # DPI not reporting HiDPI -> resolution heuristic
            scale = self.MH / 1080.0
        self.scale = max(0.75, min(4.0, scale))

        self.fam = pick_family(root)
        # Negative size == pixels, so text tracks our pixel-space layout exactly.
        self.F_TITLE = tkfont.Font(root=root, family=self.fam, size=-self.S(14), weight="bold")
        self.F_BODY  = tkfont.Font(root=root, family=self.fam, size=-self.S(13))
        self.F_SUB   = tkfont.Font(root=root, family=self.fam, size=-self.S(10))
        self.F_UI    = tkfont.Font(root=root, family=self.fam, size=-self.S(12))
        self.F_UIB   = tkfont.Font(root=root, family=self.fam, size=-self.S(12), weight="bold")
        self.F_H1    = tkfont.Font(root=root, family=self.fam, size=-self.S(17), weight="bold")

    def S(self, v) -> int:
        return int(round(v * self.scale))

    def refresh_monitor(self) -> None:
        """Re-read the primary monitor rect — the layout can change mid-session."""
        self.MW, self.MH, self.OX, self.OY = primary_monitor(
            (self.MW, self.MH, self.OX, self.OY))


def apply_ttk_style(root: tk.Tk, th: Theme) -> ttk.Style:
    """Recolour ttk's 'clam' theme with our palette (clam is the only stock theme that
    actually honours background/fieldbackground on every widget we use)."""
    st = ttk.Style(root)
    st.theme_use("clam")
    S, F_UI, F_UIB = th.S, th.F_UI, th.F_UIB

    st.configure(".", background=BG, foreground=FG, fieldbackground=CARD,
                 bordercolor=BORDER, troughcolor=BG, lightcolor=CARD, darkcolor=BG,
                 focuscolor=ACCENT, font=F_UI)
    st.configure("TFrame", background=BG)
    st.configure("Card.TFrame", background=CARD)
    st.configure("TLabel", background=BG, foreground=FG, font=F_UI)
    st.configure("Card.TLabel", background=CARD, foreground=FG, font=F_UI)
    st.configure("CardSub.TLabel", background=CARD, foreground=SUBTLE, font=th.F_SUB)
    st.configure("CardAccent.TLabel", background=CARD, foreground=ACCENT2, font=F_UIB)
    st.configure("Sub.TLabel", background=BG, foreground=SUBTLE, font=th.F_SUB)
    st.configure("H1.TLabel", background=BG, foreground=FG, font=th.F_H1)

    st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(S(10), S(8), S(10), 0))
    st.configure("TNotebook.Tab", background=BTN, foreground=SUBTLE,
                 padding=(S(18), S(8)), borderwidth=0, font=F_UIB)
    st.map("TNotebook.Tab",
           background=[("selected", CARD), ("active", BTN_HOV)],
           foreground=[("selected", FG), ("active", FG)])

    st.configure("TButton", background=BTN, foreground=FG, bordercolor=BTN_BRD,
                 borderwidth=1, padding=(S(12), S(6)), font=F_UI, relief="flat")
    st.map("TButton",
           background=[("active", BTN_HOV), ("pressed", CARD_HI), ("disabled", CARD)],
           foreground=[("disabled", SUBTLE)])
    st.configure("Accent.TButton", background=ACCENT, foreground="#0b1220", bordercolor=ACCENT)
    st.map("Accent.TButton", background=[("active", ACCENT2)])
    st.configure("Small.TButton", padding=(S(9), S(3)), font=th.F_SUB)

    st.configure("TEntry", fieldbackground=CARD, foreground=FG, bordercolor=BORDER,
                 insertcolor=FG, padding=S(5))
    st.configure("TCombobox", fieldbackground=CARD, background=BTN, foreground=FG,
                 bordercolor=BORDER, arrowcolor=SUBTLE, padding=S(5))
    st.map("TCombobox", fieldbackground=[("readonly", CARD)],
           foreground=[("readonly", FG)], background=[("active", BTN_HOV)])
    st.configure("TSpinbox", fieldbackground=CARD, foreground=FG, bordercolor=BORDER,
                 arrowcolor=SUBTLE, padding=S(4), insertcolor=FG)
    st.configure("TCheckbutton", background=BG, foreground=FG, font=F_UI,
                 indicatorcolor=CARD, indicatorbackground=CARD, focuscolor=BG)
    st.map("TCheckbutton", background=[("active", BG)],
           indicatorcolor=[("selected", ACCENT), ("active", CARD_HI)])
    st.configure("TSeparator", background=BORDER)
    st.configure("Vertical.TScrollbar", background=BTN, troughcolor=BG, bordercolor=BG,
                 arrowcolor=SUBTLE, width=S(11))
    st.map("Vertical.TScrollbar", background=[("active", BTN_HOV)])

    # The Combobox popdown is a raw Tk listbox — only option_add reaches it.
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#0b1220")
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    return st
