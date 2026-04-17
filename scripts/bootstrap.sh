#!/usr/bin/env bash
# Bootstrap and launch KosmoStream inside the codespace.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- Configuration checks ---
if [[ -z "${OWM_API_KEY:-}" ]]; then
  echo "[ERROR] OWM_API_KEY is not set. Export it before running (e.g., export OWM_API_KEY=your_key)." >&2
  exit 1
fi
if [[ -n "${OWM_ENDPOINT:-}" ]]; then
  echo "[INFO] Using custom OWM_ENDPOINT=${OWM_ENDPOINT}"
fi

# --- Data loads ---
python load_bd_calendar.py
python fetch_weather.py
python fetch_space_weather.py

# --- Launch app ---
exec python app.py
