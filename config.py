#!/usr/bin/env python3
"""Sinlate settings — defaults plus load/save of ~/.config/sinlate/config.json.

Only keys present in DEFAULTS are honoured from the user file, so a stale or hand-edited
config can never inject unknown keys into the running app.
"""
import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "sinlate"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Languages offered in the Settings dropdowns. English names — they go into the LLM prompt
# verbatim, and the model reports detected languages using the same names.
LANGUAGES = [
    "German", "English", "French", "Spanish", "Italian",
    "Portuguese", "Dutch", "Romanian", "Polish", "Russian",
]

DEFAULTS = {
    # --- behaviour ---
    # A single key is a valid shortcut; F9 is free on GNOME and needs no modifiers.
    "hotkey": "F9",
    # Auto-flip pair. lang_native is the PRIMARY target: text detected as lang_native is
    # translated into lang_other; text in any other language goes into lang_native.
    "lang_native": "German",
    "lang_other": "English",
    "popup_seconds": 5.0,
    "auto_copy": True,
    "max_chars": 4000,        # input cap; ~1100 tokens, safe inside the server's num_ctx of 4096

    # --- translation engine ---
    # The dedicated Ollama instance that local-wisprflow already runs for text cleanup
    # (wf-cleanup-llm.service). Sinlate is a second client of it — never start another one.
    "ollama_url": "http://127.0.0.1:11435",
    "llm_model": "gemma3:4b",
    "llm_timeout": 60,        # generous: covers a cold model load (5-15s) on the first call
    # Must match the instance's own OLLAMA_KEEP_ALIVE (5m). A longer value would pin the model
    # in VRAM, and the 12 GB card is shared with the resident research harness.
    "llm_keep_alive": "5m",
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text())
            cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
        except Exception as e:  # noqa: BLE001
            print(f"[sinlate] WARNING: could not read {CONFIG_PATH}: {e!r}; using defaults",
                  flush=True)
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    payload = {k: cfg[k] for k in DEFAULTS if k in cfg}
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, CONFIG_PATH)
