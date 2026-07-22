# Sinlate

Select text anywhere, press a hotkey, read the translation in a small popup at the right of
the screen. The translation lands on your clipboard too, so you can paste it straight where
you need it. Everything runs locally — no internet, no Google Translate tab.

Default hotkey: **`F9`**

The hotkey can be **a single key or a combination** — whatever you press in Settings is what
gets bound. Free single keys on this desktop include `F9`–`F12`, `Pause`, `Insert`,
`Scroll_Lock` and `Menu`. Sinlate checks your live GNOME shortcuts and refuses a key that is
already taken (it will tell you what owns it). Binding a key you type with — a letter, `space`,
`Return` — is allowed too, but it asks first, because that key then translates instead of
typing in *every* app.

## How it decides the direction

You configure a language **pair** (default German ⇄ English) and it flips automatically:

| You selected | You get |
|---|---|
| German | English |
| English | German |
| French, Spanish, anything else | German |

In Settings, "My language" is the one everything gets translated *into*; text already in that
language is translated *out* into the second language.

## Install

```bash
cd ~/Sinlate
./install.sh
```

That registers the GNOME shortcut (appending to the shared shortcut list, so the wisprflow
dictation hotkey is untouched) and adds a "Sinlate" entry to the app menu.

## Using it

- **Translate**: highlight text in any app → press the hotkey. A popup appears at the right
  edge for 5 seconds. Hover it to keep it open; click it to dismiss early.
- **Main window**: launch *Sinlate* from the app menu, or run `./sinlate-trigger show`.
  - **History** — every translation from this session, newest first, with a per-row Copy
    button. It is memory-only: quitting Sinlate clears it, nothing is written to disk.
  - **Settings** — hotkey, language pair, popup duration, auto-copy. Saved immediately to
    `~/.config/sinlate/config.json`.
- Closing the main window only hides it; the hotkey keeps working. Use **Quit Sinlate** to
  stop it entirely. Pressing the hotkey afterwards starts it again automatically.

## How it works

One resident Python process (standard library only — no venv, no pip installs):

```
GNOME hotkey → sinlate-trigger → Unix socket → Sinlate
                                                 ├─ wl-paste --primary   (what you highlighted)
                                                 ├─ gemma3:4b @ :11435   (detect + translate)
                                                 ├─ wl-copy              (result to clipboard)
                                                 └─ popup + history
```

The translation model is **gemma3:4b** on the Ollama instance at `127.0.0.1:11435` — the same
one local-wisprflow already runs for transcript cleanup. Sinlate is just a second client of
it, so there is no extra model in VRAM. `keep_alive` is 5 minutes to match that service; the
first translation after an idle gap takes ~5–10 s while the model loads, then ~1 s.

If nothing is highlighted, Sinlate falls back to the normal clipboard.

## Settings reference (`~/.config/sinlate/config.json`)

| Key | Default | Meaning |
|---|---|---|
| `hotkey` | `F9` | GNOME accelerator; a bare keysym like `F9` or a combo like `<Ctrl><Super>t` |
| `lang_native` | `German` | primary target — everything else is translated into this |
| `lang_other` | `English` | target for text already in `lang_native` |
| `popup_seconds` | `5.0` | popup lifetime |
| `auto_copy` | `true` | put the translation on the clipboard |
| `max_chars` | `4000` | input cap (the model's context is 4096 tokens) |
| `ollama_url` | `http://127.0.0.1:11435` | wisprflow's cleanup-LLM instance |
| `llm_model` | `gemma3:4b` | translation model |
| `llm_timeout` | `60` | seconds; covers a cold model load |
| `llm_keep_alive` | `5m` | must match the service's own setting |

## Troubleshooting

**"Translation engine offline"** — the Ollama instance is not running:
```bash
systemctl --user start wf-cleanup-llm.service
```

**"Model gemma3:4b is missing"**
```bash
OLLAMA_HOST=127.0.0.1:11435 ollama pull gemma3:4b
```

**Hotkey does nothing** — check what is registered, and that nothing else grabs the key:
```bash
python3 hotkey.py show
python3 hotkey.py apply F10     # bind a different key from the shell
./sinlate-trigger translate     # does the app itself work?
```
GNOME's own shortcut list is the source of truth: if you change Sinlate's shortcut in GNOME
Settings, Sinlate adopts it on the next start rather than overwriting it.

**Logs** — when started by the hotkey, output goes to `~/.cache/sinlate/sinlate.log`.

**Test the translator alone**
```bash
python3 engine.py "Wie spät ist es?"
```

## Uninstall

```bash
python3 hotkey.py remove
rm -f ~/.local/share/applications/sinlate.desktop ~/Desktop/sinlate.desktop
rm -rf ~/.config/sinlate ~/.cache/sinlate
```

## Files

| File | Role |
|---|---|
| `sinlate.py` | app controller: socket server, event pump, worker threads |
| `engine.py` | selection grabbing, the Ollama call, clipboard |
| `popup.py` | the borderless non-focus-stealing result popup |
| `mainwin.py` | history + settings window, hotkey capture |
| `theme.py` | palette, DPI scaling, monitor geometry, ttk styling |
| `hotkey.py` | GNOME shortcut registration (safe read-modify-write) |
| `config.py` | defaults and `~/.config/sinlate/config.json` |
| `sinlate-trigger` | tiny client the hotkey runs; starts the app if needed |
