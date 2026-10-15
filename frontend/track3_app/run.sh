#!/usr/bin/env bash
# Project Spoonbill, Track 3: install dependencies (first run) and launch the dashboard.
# Usage:  ./run.sh                     auto-resolve data folder (repo data/ if present, else fixtures)
#         ./run.sh --demo              demo mode (scripted click path)
#         ./run.sh --data-dir /path    explicit data folder
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for candidate in python3.13 python3.12 python3.11 python3.14 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        PY="$candidate"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "ERROR: Python 3.11 or newer was not found." >&2
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "Creating virtual environment with $PY ..."
    "$PY" -m venv .venv
fi

echo "Installing dependencies (quick when already installed) ..."
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt

if [ ! -f "assets/fonts/NotoSansTC-Regular.ttf" ]; then
    echo "WARNING: bundled CJK font missing; PDF export is disabled until you run:"
    echo "         .venv/bin/python -m pip install fonttools && .venv/bin/python scripts/fetch_fonts.py"
fi

exec .venv/bin/python -m streamlit run app.py -- "$@"
