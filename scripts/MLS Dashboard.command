#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# MLS Dashboard launcher (macOS).
# Double-click this file to start the Streamlit dashboard and open it in your
# browser. Close the Terminal window it opens to stop the server.
#
# If your MLS repo is NOT at ~/MLS, edit REPO_DIR on the next line once.
# ─────────────────────────────────────────────────────────────────────────────

REPO_DIR="$HOME/MLS"
PORT=8501

cd "$REPO_DIR" 2>/dev/null || {
  echo "❌ Could not find the MLS repo at: $REPO_DIR"
  echo "   Open this file in a text editor and set REPO_DIR to your repo path."
  echo "   (Press any key to close.)"
  read -n 1 -s
  exit 1
}

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
