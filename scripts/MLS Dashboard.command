#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# MLS Dashboard launcher (macOS).
# Serves the projections dashboard (webapp/: game-by-game projections + playoff
# / Shield standings vs naive) on a tiny local web server and opens it in your
# browser. Close the Terminal window it opens to stop the server.
#
# Repo path is pinned below for Ryan's Mac; auto-detect kicks in if it moves.
# ─────────────────────────────────────────────────────────────────────────────

REPO_DIR="$HOME/development/mls"   # pinned; auto-detect runs if this is wrong
PORT=8000

# Auto-detect the repo (folder containing webapp/index.html) if the pin is wrong.
if [ -z "$REPO_DIR" ] || [ ! -f "$REPO_DIR/webapp/index.html" ]; then
  for d in "$HOME/development/mls" "$HOME/MLS" "$HOME/Desktop/MLS" \
           "$HOME/Documents/MLS" "$HOME/Projects/MLS" "$HOME/code/MLS"; do
    if [ -f "$d/webapp/index.html" ]; then REPO_DIR="$d"; break; fi
  done
fi
# Fallback: search under $HOME (one-time, may take a few seconds).
if [ -z "$REPO_DIR" ] || [ ! -f "$REPO_DIR/webapp/index.html" ]; then
  REPO_DIR="$(find "$HOME" -maxdepth 6 -type f -path '*/webapp/index.html' 2>/dev/null \
              | head -1 | sed 's|/webapp/index.html$||')"
fi

cd "$REPO_DIR/webapp" 2>/dev/null || {
  echo "❌ Could not find the dashboard (looked for a folder containing webapp/index.html)."
  echo "   Open this file in a text editor and set REPO_DIR to your repo path."
  echo "   (Press any key to close.)"
  read -n 1 -s
  exit 1
}

# Pick an available Python for the static file server.
PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "❌ Python isn't on your PATH; can't start the local server."
  echo "   (Press any key to close.)"
  read -n 1 -s
  exit 1
fi

# Open the desktop browser once the server has had a moment to start.
( sleep 1; open "http://localhost:$PORT/" ) &

echo "──────────────────────────────────────────────"
echo "  MLS projections dashboard"
echo "  Serving: $REPO_DIR/webapp"
echo "  Desktop: http://localhost:$PORT/"
echo "  Phone:   http://<your-mac-ip>:$PORT/   (same Wi-Fi; run 'ipconfig getifaddr en0' for the IP)"
echo "  Close this window to stop the server."
echo "──────────────────────────────────────────────"

exec "$PY" -m http.server "$PORT" --bind 0.0.0.0
