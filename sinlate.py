#!/usr/bin/env python3
"""Sinlate — translate the text you have selected, with one hotkey, fully offline.

Architecture: one resident tkinter process. The GNOME hotkey runs `sinlate-trigger`, which
sends "translate" over a Unix socket. A worker thread grabs the primary selection, asks the
local gemma3:4b (Ollama :11435) to detect + translate it, copies the result, and the popup
shows it at the right edge of the screen.

Tk is not thread-safe, so the socket and worker threads only put events on a queue; a
root.after() pump drains it and does every UI call on the main thread.

Usage:  sinlate.py [--show | --hidden]
"""
import os
import queue
import socket
import sys
import threading
import time
import tkinter as tk

import engine
import hotkey
from config import load_config, save_config
from mainwin import MainWindow
from popup import TranslationPopup
from theme import OKC, REC, SUBTLE, Theme, apply_ttk_style

RUNTIME = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
SOCKET_PATH = os.path.join(RUNTIME, "sinlate.sock")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def ping_existing(command: str = "ping") -> str:
    """Talk to an already-running instance; '' if there is none."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(SOCKET_PATH)
        s.sendall(command.encode())
        reply = s.recv(64).decode("utf-8", "replace")
        s.close()
        return reply
    except OSError:
        return ""


class SinlateApp:
    def __init__(self, root: tk.Tk, th: Theme, start_hidden: bool):
        self.root, self.th = root, th
        self.cfg = load_config()
        self.history: list[dict] = []       # session only — never written to disk
        self.events: queue.Queue = queue.Queue()
        self.busy = threading.Event()
        self._srv = None
        self._stopping = False

        self.popup = TranslationPopup(root, th, self.cfg)
        self.win = MainWindow(root, th, self)
        if not start_hidden:
            self.win.show()

        threading.Thread(target=self._serve, daemon=True).start()
        self.root.after(50, self._pump)

    # -- settings -------------------------------------------------------------
    def persist(self, message: str = ""):
        try:
            save_config(self.cfg)
        except Exception as e:  # noqa: BLE001
            self.win.set_status(f"could not save settings: {e}", REC)
            return
        self.win.refresh_hotkey()
        if message:
            self.win.set_status(message, OKC)

    # -- socket ---------------------------------------------------------------
    def _serve(self):
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)          # stale socket from a crash
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o600)
        srv.listen(8)
        self._srv = srv
        log(f"listening on {SOCKET_PATH}")
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                if self._stopping:
                    break
                continue                     # survive transient errors
            with conn:
                try:
                    cmd = conn.recv(4096).decode("utf-8", "replace").strip()
                    reply = "ok"
                    if cmd == "ping":
                        reply = "pong"
                    elif cmd == "translate":
                        self.events.put(("trigger",))
                    elif cmd == "show":
                        self.events.put(("show",))
                    elif cmd == "quit":
                        reply = "bye"
                        self.events.put(("quit",))
                    else:
                        reply = f"unknown command {cmd!r}"
                    conn.sendall(reply.encode())
                except OSError:
                    pass

    # -- event pump (main thread) ---------------------------------------------
    def _pump(self):
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "trigger":
                    self.on_trigger()
                elif kind == "show":
                    self.win.show()
                elif kind == "quit":
                    self.shutdown()
                    return
                elif kind == "result":
                    self.on_result(ev[1], ev[2])
                elif kind == "error":
                    self.on_error(ev[1])
        except queue.Empty:
            pass
        self.root.after(50, self._pump)

    # -- translation ----------------------------------------------------------
    def on_trigger(self):
        if self.busy.is_set():
            return                           # coalesce rapid presses; spinner is already up
        self.busy.set()
        self.popup.show_busy()
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            text, source = engine.grab_selection()
            if not text:
                self.events.put(("error", "No text selected.\n"
                                          "Highlight something, then press the hotkey."))
                return
            truncated = len(text) > self.cfg["max_chars"]
            if truncated:
                text = text[:self.cfg["max_chars"]]
            t0 = time.time()
            result = engine.translate(self.cfg, text)
            log(f"{source}: {len(text)}ch {result['source_language']}->"
                f"{result['target_language']} in {time.time() - t0:.2f}s")

            copied = False
            if self.cfg["auto_copy"]:
                try:
                    engine.copy_to_clipboard(result["translation"])
                    copied = True
                except Exception as e:  # noqa: BLE001
                    log(f"clipboard copy failed: {e!r}")

            entry = {
                "ts": time.time(),
                "source_text": text,
                "source_language": result["source_language"],
                "target_language": result["target_language"],
                "translation": result["translation"],
                "truncated": truncated,
            }
            self.events.put(("result", entry, copied))
        except engine.EngineError as e:
            self.events.put(("error", str(e)))
        except Exception as e:  # noqa: BLE001
            log(f"unexpected failure: {e!r}")
            self.events.put(("error", f"Translation failed: {e.__class__.__name__}"))
        finally:
            self.busy.clear()

    def on_result(self, entry: dict, copied: bool):
        self.history.append(entry)
        self.win.history.add_entry(entry)
        self.popup.show_result(entry, copied)

    def on_error(self, message: str):
        self.popup.show_error(message)

    # -- lifecycle ------------------------------------------------------------
    def shutdown(self):
        self._stopping = True
        try:
            if self._srv is not None:
                self._srv.close()
        except OSError:
            pass
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass
        os._exit(0)          # decisive: no daemon thread can keep the process alive


def main() -> int:
    start_hidden = "--hidden" in sys.argv

    # Single instance: hand the request to the running copy instead of starting a second one.
    if ping_existing() == "pong":
        if not start_hidden:
            ping_existing("show")
            log("already running — raised the existing window")
        return 0

    root = tk.Tk()
    root.withdraw()                # the root only owns fonts/styles; the real windows are Toplevels
    root.title("Sinlate")
    th = Theme(root)
    apply_ttk_style(root, th)

    app = SinlateApp(root, th, start_hidden)

    # Reconcile the shortcut. gsettings is the source of truth for what the desktop actually
    # does, so an existing binding is adopted rather than overwritten — otherwise a stale
    # config would silently undo a change made in GNOME's own Settings.
    try:
        existing = hotkey.current()
        if not existing:
            hotkey.apply(app.cfg["hotkey"])
            log(f"registered hotkey {app.cfg['hotkey']}")
        elif existing != app.cfg["hotkey"]:
            log(f"adopting hotkey {existing} from GNOME (config had {app.cfg['hotkey']})")
            app.cfg["hotkey"] = existing
            save_config(app.cfg)
            app.win.refresh_hotkey()
    except Exception as e:  # noqa: BLE001
        log(f"could not register hotkey: {e!r}")

    log(f"ready — {app.cfg['lang_native']} <-> {app.cfg['lang_other']}, "
        f"hotkey {app.cfg['hotkey']}")
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
