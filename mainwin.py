#!/usr/bin/env python3
"""Sinlate's main window — session history and settings.

Deliberately not shown on each translation: closing it only hides it, the app keeps running
and the hotkey keeps working. History lives in memory and dies with the app, by design.
"""
import time
import tkinter as tk
from tkinter import ttk

import engine
import hotkey
from config import LANGUAGES, save_config
from theme import ACCENT, ACCENT2, BG, BORDER, CARD, FG, OKC, REC, SUBTLE, Theme

# tkinter event.state bits -> GNOME accelerator modifiers (Mod2 = NumLock etc. are ignored)
_MOD_BITS = ((0x0004, "<Ctrl>"), (0x0001, "<Shift>"), (0x0008, "<Alt>"), (0x0040, "<Super>"))
_PURE_MODIFIERS = {
    "Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
    "Meta_L", "Meta_R", "Hyper_L", "Hyper_R", "ISO_Level3_Shift", "Caps_Lock", "Num_Lock",
}


def confirm(parent, th: Theme, title: str, message: str,
            ok_text: str = "Use it anyway", cancel_text: str = "Pick another") -> bool:
    """Small themed modal — a raw Tk messagebox would look foreign next to the rest."""
    S = th.S
    top = parent.winfo_toplevel()
    dlg = tk.Toplevel(top)
    dlg.title(title)
    dlg.configure(bg=BG)
    dlg.transient(top)
    dlg.resizable(False, False)

    frm = ttk.Frame(dlg, padding=(S(22), S(18)))
    frm.pack(fill="both", expand=True)
    ttk.Label(frm, text=title, style="H1.TLabel").pack(anchor="w")
    ttk.Label(frm, text=message, style="Sub.TLabel", justify="left",
              wraplength=S(400)).pack(anchor="w", pady=(S(10), S(18)))

    result = {"ok": False}
    btns = ttk.Frame(frm)
    btns.pack(anchor="e")

    def accept():
        result["ok"] = True
        dlg.destroy()

    ttk.Button(btns, text=cancel_text, command=dlg.destroy).pack(side="left", padx=(0, S(8)))
    ttk.Button(btns, text=ok_text, style="Accent.TButton", command=accept).pack(side="left")

    dlg.update_idletasks()
    x = top.winfo_rootx() + (top.winfo_width() - dlg.winfo_width()) // 2
    y = top.winfo_rooty() + (top.winfo_height() - dlg.winfo_height()) // 3
    dlg.geometry(f"+{max(0, x)}+{max(0, y)}")
    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    dlg.grab_set()
    dlg.wait_window()
    return result["ok"]


class HotkeyCapture(ttk.Frame):
    """Click, press any key or combination, and it becomes the GNOME shortcut.

    A single key (F9, Pause, Insert …) is just as valid as a combination — no modifier is
    required. Keys that normal typing depends on still work, but ask for confirmation first.
    """

    def __init__(self, master, th: Theme, initial: str, on_change):
        super().__init__(master)
        self.th, self.on_change = th, on_change
        self.value = initial
        self.capturing = False
        self.var = tk.StringVar(value=hotkey.pretty(initial))
        self.entry = ttk.Entry(self, textvariable=self.var, state="readonly",
                               width=24, font=th.F_UIB, justify="center")
        self.entry.pack(side="left", ipady=th.S(2))
        self.btn = ttk.Button(self, text="Change…", command=self.start)
        self.btn.pack(side="left", padx=(th.S(8), 0))
        self.hint = ttk.Label(self, text="", style="Sub.TLabel")
        self.hint.pack(side="left", padx=(th.S(10), 0))

    def start(self):
        if self.capturing:
            return
        self.capturing = True
        self.var.set("Press a key…")
        self.hint.configure(text="single key or combination · Esc cancels", foreground=SUBTLE)
        self.btn.state(["disabled"])
        self.entry.focus_set()
        self.entry.grab_set()
        self.entry.bind("<KeyPress>", self._on_key)

    def _teardown(self):
        """Release the keyboard before anything else can open a window."""
        self.entry.grab_release()
        self.entry.unbind("<KeyPress>")
        self.btn.state(["!disabled"])
        self.capturing = False

    def _report(self, value: str | None, message: str = "", colour: str = SUBTLE):
        if value:
            self.value = value
        self.var.set(hotkey.pretty(self.value))
        self.hint.configure(text=message, foreground=colour)
        if message:
            self.after(4000, lambda: self.hint.configure(text=""))

    def _on_key(self, event):
        keysym = event.keysym
        if keysym == "Escape":
            self._teardown()
            self._report(None, "cancelled")
            return "break"
        if keysym in _PURE_MODIFIERS:
            return "break"                      # a modifier alone cannot be a shortcut

        mods = [name for bit, name in _MOD_BITS if event.state & bit]
        key = keysym.lower() if len(keysym) == 1 and keysym.isalpha() else keysym
        combo = "".join(mods) + key

        self._teardown()

        clash = hotkey.conflict(combo)
        if clash:
            self._report(None, f"already used by {clash}", REC)
            return "break"

        warning = hotkey.risky(combo)
        if warning and not confirm(
                self, self.th, "Use a typing key as the hotkey?",
                f"{warning}. If you bind it, pressing it will translate instead of "
                f"typing — in every app, not just this one.\n\n"
                f"Keys like F9, Pause, Insert or Menu are safer single-key choices."):
            self._report(None, "cancelled")
            return "break"

        try:
            hotkey.set_binding_only(combo)
        except Exception as e:  # noqa: BLE001
            self._report(None, f"could not set: {e}", REC)
            return "break"
        self._report(combo, "saved", OKC)
        self.on_change(combo)
        return "break"


class HistoryTab(ttk.Frame):
    """Scrollable list of this session's translations, newest first."""

    def __init__(self, master, th: Theme):
        super().__init__(master)
        self.th = th
        S = th.S

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                            style="Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = ttk.Frame(self.canvas)
        self.win_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self.win_id, width=e.width))
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", lambda _e: self._bind_wheel(True))
            w.bind("<Leave>", lambda _e: self._bind_wheel(False))

        self.empty = ttk.Label(
            self.inner, style="Sub.TLabel", justify="center",
            text="\nNo translations yet.\n\n"
                 "Select text anywhere, press your hotkey,\n"
                 "and it shows up here.")
        self.empty.pack(pady=S(40))
        self._cards = []

    def _bind_wheel(self, on: bool):
        if on:
            self.canvas.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-2, "units"))
            self.canvas.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(2, "units"))
            self.canvas.bind_all(
                "<MouseWheel>",
                lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        else:
            for seq in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
                self.canvas.unbind_all(seq)

    def add_entry(self, entry: dict):
        S, th = self.th.S, self.th
        if not self._cards:
            self.empty.pack_forget()

        card = ttk.Frame(self.inner, style="Card.TFrame", padding=(S(14), S(10)))
        if self._cards:
            card.pack(fill="x", padx=S(12), pady=(S(8), 0), before=self._cards[0])
        else:
            card.pack(fill="x", padx=S(12), pady=(S(8), 0))
        self._cards.insert(0, card)

        head = ttk.Frame(card, style="Card.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=time.strftime("%H:%M:%S", time.localtime(entry["ts"])),
                  style="CardSub.TLabel").pack(side="left")
        arrow = f"{entry['source_language']}  →  {entry['target_language']}"
        if entry.get("truncated"):
            arrow += "  ·  truncated"
        ttk.Label(head, text=arrow, style="CardAccent.TLabel").pack(side="left", padx=(S(12), 0))

        copy_btn = ttk.Button(head, text="Copy", style="Small.TButton")
        copy_btn.pack(side="right")

        def do_copy():
            engine.copy_to_clipboard(entry["translation"])
            copy_btn.configure(text="Copied ✓")
            copy_btn.after(1200, lambda: copy_btn.configure(text="Copy"))

        copy_btn.configure(command=do_copy)

        src = entry["source_text"]
        if len(src) > 400:
            src = src[:400].rstrip() + "…"
        for text, style in ((src, "CardSub.TLabel"), (entry["translation"], "Card.TLabel")):
            lbl = ttk.Label(card, text=text, style=style, justify="left", wraplength=S(600))
            lbl.pack(fill="x", anchor="w", pady=(S(6), 0))
            # Keep wrapping in step with the window width.
            lbl.bind("<Configure>",
                     lambda e: e.widget.configure(wraplength=max(200, e.widget.winfo_width() - 8)))

        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.yview_moveto(0.0)


class SettingsTab(ttk.Frame):
    def __init__(self, master, th: Theme, app):
        super().__init__(master, padding=(th.S(22), th.S(18)))
        self.th, self.app = th, app
        S, cfg = th.S, app.cfg
        row = 0

        def section(text):
            nonlocal row
            ttk.Label(self, text=text, style="H1.TLabel").grid(
                row=row, column=0, columnspan=3, sticky="w", pady=(S(14) if row else 0, S(6)))
            row += 1

        def hint(text):
            nonlocal row
            ttk.Label(self, text=text, style="Sub.TLabel", justify="left").grid(
                row=row, column=0, columnspan=3, sticky="w", pady=(0, S(8)))
            row += 1

        section("Hotkey")
        hint("Select text in any app, then press this to translate it.\n"
             "A single key works too — F9, Pause, Insert or Menu are good free ones.")
        self.capture = HotkeyCapture(self, th, cfg["hotkey"], self._on_hotkey)
        self.capture.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, S(4)))
        row += 1

        section("Languages")
        hint("Text in your language is translated out; anything else is translated in.")

        self.native = tk.StringVar(value=cfg["lang_native"])
        self.other = tk.StringVar(value=cfg["lang_other"])
        ttk.Label(self, text="My language").grid(row=row, column=0, sticky="w", pady=S(4))
        cb1 = ttk.Combobox(self, textvariable=self.native, values=LANGUAGES,
                           state="readonly", width=16)
        cb1.grid(row=row, column=1, sticky="w", padx=(S(10), 0))
        ttk.Button(self, text="⇄  Swap", command=self._swap).grid(
            row=row, column=2, sticky="w", padx=(S(12), 0))
        row += 1
        ttk.Label(self, text="Translated into").grid(row=row, column=0, sticky="w", pady=S(4))
        cb2 = ttk.Combobox(self, textvariable=self.other, values=LANGUAGES,
                           state="readonly", width=16)
        cb2.grid(row=row, column=1, sticky="w", padx=(S(10), 0))
        row += 1
        self.pair_lbl = ttk.Label(self, style="Sub.TLabel")
        self.pair_lbl.grid(row=row, column=0, columnspan=3, sticky="w", pady=(S(6), 0))
        row += 1
        for cb in (cb1, cb2):
            cb.bind("<<ComboboxSelected>>", lambda _e: self._on_langs())

        section("Popup")
        self.secs = tk.DoubleVar(value=cfg["popup_seconds"])
        ttk.Label(self, text="Show for").grid(row=row, column=0, sticky="w", pady=S(4))
        sp = ttk.Spinbox(self, from_=2, to=30, increment=1, width=6, textvariable=self.secs,
                         command=self._on_popup)
        sp.grid(row=row, column=1, sticky="w", padx=(S(10), 0))
        sp.bind("<FocusOut>", lambda _e: self._on_popup())
        sp.bind("<Return>", lambda _e: self._on_popup())
        ttk.Label(self, text="seconds  (hover the popup to keep it open)",
                  style="Sub.TLabel").grid(row=row, column=2, sticky="w", padx=(S(8), 0))
        row += 1

        self.autocopy = tk.BooleanVar(value=cfg["auto_copy"])
        ttk.Checkbutton(self, text="Copy the translation to the clipboard automatically",
                        variable=self.autocopy, command=self._on_autocopy).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(S(10), 0))
        row += 1

        section("Engine")
        self.engine_lbl = ttk.Label(self, style="Sub.TLabel", justify="left")
        self.engine_lbl.grid(row=row, column=0, columnspan=3, sticky="w")
        self.engine_lbl.configure(
            text=f"{cfg['llm_model']} on {cfg['ollama_url']}  ·  fully offline\n"
                 f"Shared with local-wisprflow's cleanup model — no extra memory used.")
        row += 1

        self.columnconfigure(2, weight=1)
        self._refresh_pair()

    def _refresh_pair(self):
        n, o = self.native.get(), self.other.get()
        self.pair_lbl.configure(text=f"{n} → {o}    ·    everything else → {n}")

    def _swap(self):
        n, o = self.native.get(), self.other.get()
        self.native.set(o)
        self.other.set(n)
        self._on_langs()

    def _on_langs(self):
        if self.native.get() == self.other.get():
            # A pair of one language has no direction; nudge the other side off it.
            alt = "English" if self.native.get() != "English" else "German"
            self.other.set(alt)
        self.app.cfg["lang_native"] = self.native.get()
        self.app.cfg["lang_other"] = self.other.get()
        self._refresh_pair()
        self.app.persist("languages saved")

    def _on_popup(self):
        try:
            v = float(self.secs.get())
        except (tk.TclError, ValueError):
            return
        self.app.cfg["popup_seconds"] = max(2.0, min(30.0, v))
        self.app.persist("popup duration saved")

    def _on_autocopy(self):
        self.app.cfg["auto_copy"] = bool(self.autocopy.get())
        self.app.persist("clipboard setting saved")

    def _on_hotkey(self, combo: str):
        self.app.cfg["hotkey"] = combo
        self.app.persist(f"hotkey set to {combo}")


class MainWindow:
    def __init__(self, root: tk.Tk, th: Theme, app):
        self.th, self.app = th, app
        S = th.S
        w = tk.Toplevel(root)
        w.title("Sinlate")
        w.configure(bg=BG)
        w.geometry(f"{S(780)}x{S(560)}")
        w.minsize(S(560), S(380))
        # Closing hides the window; the app stays resident so the hotkey keeps working.
        w.protocol("WM_DELETE_WINDOW", self.hide)
        w.withdraw()
        self.win = w

        header = ttk.Frame(w, padding=(S(18), S(14), S(18), S(4)))
        header.pack(fill="x")
        ttk.Label(header, text="Sinlate", style="H1.TLabel").pack(side="left")
        ttk.Label(header, text="  offline translator", style="Sub.TLabel").pack(
            side="left", padx=(S(6), 0))
        self.hotkey_lbl = ttk.Label(header, style="Sub.TLabel")
        self.hotkey_lbl.pack(side="right")

        nb = ttk.Notebook(w)
        nb.pack(fill="both", expand=True, padx=S(10), pady=(0, S(6)))
        self.history = HistoryTab(nb, th)
        self.settings = SettingsTab(nb, th, app)
        nb.add(self.history, text="History")
        nb.add(self.settings, text="Settings")

        bar = ttk.Frame(w, padding=(S(18), S(6), S(18), S(12)))
        bar.pack(fill="x")
        self.status = ttk.Label(bar, text="", style="Sub.TLabel")
        self.status.pack(side="left")
        ttk.Button(bar, text="Quit Sinlate", command=app.shutdown).pack(side="right")
        ttk.Button(bar, text="Hide", command=self.hide).pack(side="right", padx=(0, S(8)))
        self.refresh_hotkey()

    def refresh_hotkey(self):
        self.hotkey_lbl.configure(text=f"hotkey  {hotkey.pretty(self.app.cfg['hotkey'])}")

    def set_status(self, text: str, colour: str = SUBTLE):
        self.status.configure(text=text, foreground=colour)
        if text:
            self.status.after(3000, lambda: self.status.configure(text=""))

    def show(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def hide(self):
        self.win.withdraw()
