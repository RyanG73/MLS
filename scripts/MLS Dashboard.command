#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# MLS Dashboard launcher (macOS).
# Double-click this file to start the Streamlit dashboard and open it in your
# browser. Close the Terminal window it opens to stop the server.
#
# The repo location is auto-detected. To pin it explicitly, set REPO_DIR below.
# ─────────────────────────────────────────────────────────────────────────────

REPO_DIR=""          # leave empty to auto-detect; or hardcode e.g. "$HOME/code/MLS"
PORT=8501

# Auto-detect the repo (the folder containing dashboard/app.py) if not pinned.
if [ -z "$REPO_DIR" ] || [ ! -f "$REPO_DIR/dashboard/app.py" ]; then
  for d in "$HOME/MLS" "$HOME/Desktop/MLS" "$HOME/Documents/MLS" \
           "$HOME/Projects/MLS" "$HOME/projects/MLS" "$HOME/code/MLS" "$HOME/repos/MLS"; do
    if [ -f "$d/dashboard/app.py" ]; then REPO_DIR="$d"; break; fi
  done
fi
# Fallback: search under $HOME (one-time, may take a few seconds).
if [ -z "$REPO_DIR" ] || [ ! -f "$REPO_DIR/dashboard/app.py" ]; then
  REPO_DIR="$(find "$HOME" -maxdepth 6 -type f -path '*/dashboard/app.py' 2>/dev/null \
              | head -1 | sed 's|/dashboard/app.py$||')"
fi

cd "$REPO_DIR" 2>/dev/null || {
  echo "❌ Could not locate the MLS repo (looked for a folder containing dashboard/app.py)."
  echo "   Open this file in a text editor and set REPO_DIR to your repo path."
  echo "   (Press any key to close.)"
  read -n 1 -s
  exit 1
}
echo "Using repo: $REPO_DIR"

# Activate the virtualenv if it exists.
if [ -f "venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

# Make sure Streamlit is available; offer to install deps if not.
if ! python -c "import streamlit" 2>/dev/null; then
  echo "⚠️  Streamlit isn't installed in this environment."
  if [ -f "requirements.txt" ]; then
    echo "   Installing dependencies (one-time)…"
    pip install -r requirements.txt || { echo "Install failed."; read -n 1 -s; exit 1; }
  else
    echo "   Run: pip install streamlit"
    read -n 1 -s
    exit 1
  fi
fi

# Open the desktop browser once the server has had a moment to start.
( sleep 3; open "http://localhost:$PORT" ) &

echo "──────────────────────────────────────────────"
echo "  Starting MLS dashboard on port $PORT"
echo "  Desktop:  http://localhost:$PORT"
echo "  Phone:    use the 'Network URL' printed below"
echo "            (same Wi-Fi as this computer)"
echo "  Close this window to stop the server."
echo "──────────────────────────────────────────────"

exec streamlit run dashboard/app.py --server.port "$PORT" --server.address 0.0.0.0
