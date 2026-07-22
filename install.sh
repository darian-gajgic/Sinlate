#!/usr/bin/env bash
# Set up Sinlate: hotkey, app-menu entry, and a health check of the local translation model.
# No sudo, no systemd — Sinlate is a plain user app.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> making scripts executable"
chmod +x "$HERE/sinlate.py" "$HERE/sinlate-trigger" "$HERE/hotkey.py" "$HERE/engine.py"

echo "==> registering the GNOME hotkey"
# Appends to the shared custom-keybindings list; other apps' shortcuts are preserved.
python3 "$HERE/hotkey.py" apply

echo "==> installing the app-menu entry"
mkdir -p "$HOME/.local/share/applications"
install -m 644 "$HERE/sinlate.desktop" "$HOME/.local/share/applications/sinlate.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi
if [ -d "$HOME/Desktop" ]; then
  install -m 755 "$HERE/sinlate.desktop" "$HOME/Desktop/sinlate.desktop"
  gio set "$HOME/Desktop/sinlate.desktop" metadata::trusted true 2>/dev/null || true
fi

echo "==> checking the local translation model"
URL="$(python3 -c "from config import load_config; print(load_config()['ollama_url'])" 2>/dev/null || echo http://127.0.0.1:11435)"
MODEL="$(python3 -c "from config import load_config; print(load_config()['llm_model'])" 2>/dev/null || echo gemma3:4b)"
cd "$HERE"
if tags="$(curl -s --max-time 4 "$URL/api/tags" 2>/dev/null)"; then
  if printf '%s' "$tags" | grep -q "$MODEL"; then
    echo "    OK: $MODEL is available on $URL"
  else
    echo "    WARNING: $MODEL is not on $URL"
    echo "    Pull it with:  OLLAMA_HOST=${URL#http://} ollama pull $MODEL"
  fi
else
  echo "    WARNING: nothing is answering on $URL"
  echo "    That is local-wisprflow's cleanup model service. Start it with:"
  echo "      systemctl --user start wf-cleanup-llm.service"
fi

cat <<EOF

Done.

  Try it:   select any text, then press $(python3 -c "from config import load_config; print(load_config()['hotkey'])")
  Window:   launch "Sinlate" from the app menu (history + settings)
  Uninstall: python3 $HERE/hotkey.py remove && rm -f ~/.local/share/applications/sinlate.desktop
EOF
