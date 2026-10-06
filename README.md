# Sinlate

Select text anywhere, press a hotkey, and read the translation in a small popup at the right edge of the screen. The translation also lands on your clipboard, ready to paste. A local LLM does the work, so no text is sent to an online translator.

## Why

Translating a sentence normally means copying it into a browser tab. Sinlate does it in place, with one key press, and keeps the text on your machine.

## How it decides the direction

You configure a language pair (default German and English) and the direction flips automatically:

| You selected | You get |
|---|---|
| German | English |
| English | German |
| Anything else (French, Spanish, ...) | German |

"My language" in Settings is the language everything is translated into. Text already in that language is translated into the second language.

## Requirements

- Linux with GNOME on Wayland. The hotkey is a GNOME custom shortcut, and the selection is read with `wl-paste`.
- Python 3 with Tkinter (`python3-tk`). Standard library only: no virtualenv, no pip installs.
- `wl-clipboard`.
- An Ollama server with `gemma3:4b`. The default URL, `http://127.0.0.1:11435`, is the cleanup instance that [local-wisprflow](https://github.com/darian-gajgic/local-wisprflow) runs, so the model is shared rather than loaded twice. Any Ollama server works through the `ollama_url` setting.

## Install

```bash
git clone https://github.com/darian-gajgic/Sinlate.git
cd Sinlate
./install.sh
```

`install.sh` registers the GNOME shortcut (default `F9`), adds a "Sinlate" entry to the app menu and checks that the model is available. It appends to the shared shortcut list, so other custom shortcuts stay untouched. The app-menu entry in `sinlate.desktop` contains the absolute path of the original install; adjust its `Exec` line if your clone lives elsewhere.

## Usage

- **Translate:** highlight text in any app and press the hotkey. The popup stays for 5 seconds; hover to keep it, click to dismiss. If nothing is highlighted, Sinlate uses the clipboard.
- **Main window:** open *Sinlate* from the app menu or run `./sinlate-trigger show`.
  - *History* lists this session's translations with a Copy button per row. It lives in memory only and is cleared when Sinlate quits.
  - *Settings* covers the hotkey, language pair, popup duration and auto-copy, saved to `~/.config/sinlate/config.json`.
- Closing the window only hides it. **Quit Sinlate** stops the app; the next hotkey press starts it again.

The hotkey can be a single key or a combination. Sinlate reads the live GNOME shortcuts and refuses a key that is already taken, naming its owner. It asks before binding a typing key such as a letter or `space`, because that key would then translate instead of type in every app.

## How it works

One resident Python process:

```
GNOME hotkey -> sinlate-trigger -> Unix socket -> Sinlate
                                                    |- wl-paste --primary  (the highlighted text)
                                                    |- gemma3:4b on Ollama (detect + translate)
                                                    |- wl-copy             (result to clipboard)
                                                    '- popup + history
```

## Settings (`~/.config/sinlate/config.json`)

| Key | Default | Meaning |
|---|---|---|
| `hotkey` | `F9` | GNOME accelerator: a key such as `F9` or a combination such as `<Ctrl><Super>t` |
| `lang_native` | `German` | Target for everything not already in this language |
| `lang_other` | `English` | Target for text already in `lang_native` |
| `popup_seconds` | `5.0` | Popup lifetime |
| `auto_copy` | `true` | Put the translation on the clipboard |
| `max_chars` | `4000` | Input cap (the model context is 4096 tokens) |
| `ollama_url` | `http://127.0.0.1:11435` | Ollama server |
| `llm_model` | `gemma3:4b` | Translation model |
| `llm_timeout` | `60` | Seconds, enough for a cold model load |
| `llm_keep_alive` | `5m` | Keep in line with the Ollama service's own setting |

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Translation engine offline" | Start the Ollama instance, for example `systemctl --user start wf-cleanup-llm.service` |
| "Model gemma3:4b is missing" | `OLLAMA_HOST=127.0.0.1:11435 ollama pull gemma3:4b` |
| Hotkey does nothing | `python3 hotkey.py show` to inspect, `python3 hotkey.py apply F10` to rebind, `./sinlate-trigger translate` to test the app |
| Need the logs | `~/.cache/sinlate/sinlate.log` when started by the hotkey |
| Test the translator alone | `python3 engine.py "Wie spät ist es?"` |

GNOME's shortcut list is the source of truth. If you change the shortcut in GNOME Settings, Sinlate adopts it on the next start.

## Uninstall

```bash
python3 hotkey.py remove
rm -f ~/.local/share/applications/sinlate.desktop ~/Desktop/sinlate.desktop
rm -rf ~/.config/sinlate ~/.cache/sinlate
```

## Files

| File | Role |
|---|---|
| `sinlate.py` | App controller: socket server, event pump, worker threads |
| `engine.py` | Selection grabbing, the Ollama call, clipboard |
| `popup.py` | Borderless popup that does not steal focus |
| `mainwin.py` | History and settings window, hotkey capture |
| `theme.py` | Palette, DPI scaling, monitor geometry |
| `hotkey.py` | GNOME shortcut registration (read, modify, write) |
| `config.py` | Defaults and config file handling |
| `sinlate-trigger` | Small client the hotkey runs; starts the app if needed |

## Tested on

GNOME on Wayland on the same laptop as local-wisprflow, sharing its `gemma3:4b` instance. There, the first translation after an idle gap took about 5 to 10 s while the model loaded, and about 1 s after that.
