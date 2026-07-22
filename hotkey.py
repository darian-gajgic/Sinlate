#!/usr/bin/env python3
"""Register Sinlate's GNOME custom keyboard shortcut via gsettings.

The custom-keybindings list is shared by every app on the desktop — local-wisprflow already
has an entry in it. So this does a read-modify-write and APPENDS; overwriting the list would
silently delete the dictation hotkey.

CLI:
    python3 hotkey.py show
    python3 hotkey.py apply ['<Ctrl><Super>t']
    python3 hotkey.py remove
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

BASE = "org.gnome.settings-daemon.plugins.media-keys"
PATHID = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/sinlate/"
SCHEMA = f"{BASE}.custom-keybinding:{PATHID}"
NAME = "Sinlate translate"
COMMAND = str(Path(__file__).resolve().parent / "sinlate-trigger")

# Schemas that hold desktop-wide shortcuts. Scanned live so conflict detection reflects what
# is actually bound on this machine rather than a hardcoded guess.
_SCAN_SCHEMAS = (
    "org.gnome.desktop.wm.keybindings",
    "org.gnome.settings-daemon.plugins.media-keys",
    "org.gnome.shell.keybindings",
    "org.gnome.mutter.keybindings",
    "org.gnome.mutter.wayland.keybindings",
)

# Bare keys that normal typing and navigation depend on. Binding one of these globally takes
# it away from every other app, so the Settings tab asks for confirmation first.
_TYPING_KEYS = {
    "space", "Return", "KP_Enter", "Tab", "BackSpace", "Delete", "Escape",
    "Left", "Right", "Up", "Down", "Home", "End", "Page_Up", "Page_Down",
}


class HotkeyError(Exception):
    pass


def _get(schema: str, key: str) -> str:
    return subprocess.check_output(["gsettings", "get", schema, key], text=True).strip()


def _set(schema: str, key: str, value: str) -> None:
    subprocess.run(["gsettings", "set", schema, key, value], check=True)


def _list_paths() -> list:
    cur = _get(BASE, "custom-keybindings")
    if cur in ("@as []", "[]", ""):
        return []
    try:
        return list(ast.literal_eval(cur))   # GVariant 'as' prints as a Python-parsable list
    except Exception as e:  # noqa: BLE001
        raise HotkeyError(f"could not parse custom-keybindings: {cur!r}") from e


def _write_paths(paths: list) -> None:
    _set(BASE, "custom-keybindings", "[" + ", ".join(f"'{p}'" for p in paths) + "]")


def _norm(binding: str) -> str:
    """GNOME writes Ctrl three different ways; compare them as one."""
    return binding.replace("<Primary>", "<Ctrl>").replace("<Control>", "<Ctrl>")


def _split(binding: str) -> tuple[set, str]:
    mods = {m.replace("Primary", "Ctrl").replace("Control", "Ctrl")
            for m in re.findall(r"<([A-Za-z]+)>", binding)}
    return mods, re.sub(r"<[^>]*>", "", binding)


def taken_bindings() -> dict:
    """Every shortcut currently claimed on this desktop -> a human name for its owner."""
    out = {}
    for schema in _SCAN_SCHEMAS:
        try:
            text = subprocess.check_output(["gsettings", "list-recursively", schema],
                                           text=True, timeout=5)
        except Exception:  # noqa: BLE001
            continue
        for line in text.splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 3:
                continue
            _schema, key, value = parts
            value = value.strip()
            if not value.startswith("["):      # keybindings are stored as string arrays
                continue
            try:
                values = ast.literal_eval(value)
            except Exception:  # noqa: BLE001
                continue
            for v in values:
                # Skip the custom-keybindings list itself, whose members are dconf paths.
                if isinstance(v, str) and v and not v.startswith("/"):
                    out.setdefault(_norm(v), f"GNOME · {key.replace('-', ' ')}")

    # Other apps' custom shortcuts (local-wisprflow's dictation key lives here).
    try:
        for path in _list_paths():
            if path == PATHID:
                continue
            sch = f"{BASE}.custom-keybinding:{path}"
            try:
                binding = _get(sch, "binding").strip("'")
                name = _get(sch, "name").strip("'")
            except Exception:  # noqa: BLE001
                continue
            if binding:
                out[_norm(binding)] = name or path.rstrip("/").rsplit("/", 1)[-1]
    except HotkeyError:
        pass
    return out


def conflict(binding: str) -> str | None:
    """Name of whatever already uses this binding, or None if it is free."""
    return taken_bindings().get(_norm(binding))


def risky(binding: str) -> str | None:
    """Warning if binding this would steal a key that normal typing needs, else None.

    Single keys are perfectly allowed — this only flags the ones you would miss, like a
    letter or Return. F-keys, Pause, Insert, Menu and friends come back clean.
    """
    mods, key = _split(binding)
    if mods - {"Shift"}:            # Ctrl/Alt/Super present -> cannot collide with typing
        return None
    if len(key) == 1:
        return f"“{key}” is a normal typing key"
    if key in _TYPING_KEYS:
        return f"“{key}” is used for typing and navigation"
    if key.startswith("KP_"):
        return f"“{key}” is a numpad key"
    return None


def pretty(binding: str) -> str:
    """'<Ctrl><Super>t' -> 'Ctrl + Super + T';  'F9' -> 'F9'."""
    if not binding:
        return "(none)"
    mods, key = _split(binding)
    order = [m for m in ("Ctrl", "Shift", "Alt", "Super") if m in mods]
    label = key.upper() if len(key) == 1 else key
    return "  +  ".join(order + [label])


def apply(binding: str) -> None:
    """Create/update Sinlate's entry, preserving every other app's shortcuts."""
    paths = _list_paths()
    if PATHID not in paths:
        paths.append(PATHID)
        _write_paths(paths)
    _set(SCHEMA, "name", NAME)
    _set(SCHEMA, "command", COMMAND)
    _set(SCHEMA, "binding", binding)


def set_binding_only(binding: str) -> None:
    """Fast path used by the Settings tab once the entry already exists."""
    if PATHID not in _list_paths():
        apply(binding)
    else:
        _set(SCHEMA, "binding", binding)


def remove() -> None:
    paths = [p for p in _list_paths() if p != PATHID]
    _write_paths(paths)
    subprocess.run(["gsettings", "reset-recursively", SCHEMA], check=False)


def current() -> str:
    try:
        return _get(SCHEMA, "binding").strip("'")
    except subprocess.CalledProcessError:
        return ""


def show() -> None:
    print(f"custom-keybindings = {_get(BASE, 'custom-keybindings')}")
    if PATHID in _list_paths():
        for k in ("name", "command", "binding"):
            print(f"  sinlate {k:8s} = {_get(SCHEMA, k)}")
    else:
        print("  sinlate: not registered")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "apply":
        from config import load_config
        b = sys.argv[2] if len(sys.argv) > 2 else load_config()["hotkey"]
        apply(b)
        print(f"Bound  {b}  ->  {COMMAND}")
        show()
    elif cmd == "remove":
        remove()
        print("Removed Sinlate shortcut.")
        show()
    else:
        show()
