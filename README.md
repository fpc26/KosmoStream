# KosmoStream

KosmoStream is a cosmic-aligned planting dashboard with two UIs:

- **Flask streaming UI** (`templates/index.html`) — a full-screen, slide-based dashboard served by the Flask backend. Designed for kiosk displays and mobile browsers. Supports swipe navigation, background music, and optional voice announcements.
- **Svelte web app** (`web/`) — a lightweight browser-first frontend (Svelte 5 + Vite) that reads live data from the Flask `/api/status` endpoint. Suitable for static hosting on GitHub Pages.

Both UIs pull from the same data sources: biodynamic calendar, OpenWeatherMap forecast, and NOAA space-weather.

---

## Quick start (bootstrap script)

```bash
export OWM_API_KEY=your_openweather_key
bash scripts/bootstrap.sh
```

This loads the BD calendar, fetches weather and space weather, then starts the Flask server on port 5000. The server performs an automatic once-per-day data refresh while running, so long-lived processes stay current.

---

## Manual backend run

```bash
export OWM_API_KEY=your_openweather_key
python load_bd_calendar.py        # imports bd_calendar_*.json files into SQLite
python fetch_weather.py           # fetches 5-day forecast from OpenWeatherMap
python fetch_space_weather.py     # fetches Kp index from NOAA
python app.py                     # starts Flask on http://localhost:5000
```

---

## Environment variables

### Required

| Variable | Description |
|---|---|
| `OWM_API_KEY` | OpenWeatherMap API key (free tier supported) |

### Location & timezone

| Variable | Default | Description |
|---|---|---|
| `WX_LAT` / `LAT` | `40.0942` | Latitude for weather and astronomical calculations |
| `WX_LON` / `LON` | `-75.9097` | Longitude for weather and astronomical calculations |
| `ASTRO_TZ` | system local | IANA timezone name for rise/set times (e.g. `America/New_York`) |

### Optional features

| Variable | Default | Description |
|---|---|---|
| `API_CORS_ORIGIN` | _(unset)_ | Allowed CORS origin for `/api/status` (e.g. `https://<user>.github.io`) |
| `OWM_ENDPOINT` | OWM 5-day/3-hour endpoint | Override the OpenWeatherMap forecast URL |
| `FLASK_DEBUG` | `false` | Enable Flask debug mode |
| `TTS_ENABLED` | `false` | Enable voice announcements on page load |
| `PIPER_ENABLED` | `true` | Allow Piper TTS engine to be used |
| `PIPER_MODEL_PATH` | _(unset)_ | Path to a `.onnx` Piper voice model |
| `PIPER_BINARY` | `piper` | Piper executable name or path |
| `PIPER_PLAY_CMD` | `aplay` | Audio playback command used by Piper (e.g. `aplay` on Linux) |

> TTS requires Piper installed and `PIPER_MODEL_PATH` set. A sample model (`en_US-bryce-medium.onnx`) is included in the repo root for reference.

---

## Biodynamic calendar data

BD data is stored in `bd_calendar_YYYY.json` files (one per year). `load_bd_calendar.py` automatically discovers and loads all matching files into SQLite, so adding a new year's file and restarting is all that is needed to extend coverage.

---

## Astronomical calculations

Sun/moon rise and set times are computed using [Skyfield](https://rhodesmill.org/skyfield/) with the included `de421.bsp` ephemeris file. If Skyfield is not installed, rise/set data is silently omitted without breaking other functionality.

---

## Background music

Place `.mp3`, `.wav`, `.ogg`, or `.m4a` files in `static/music/`. The Flask UI will serve them as a looping playlist via the in-page audio player. The mute toggle in Settings persists across reloads.

---

## Svelte web frontend (local)

From `./web`:

```bash
npm install
npm run dev
```

Optional: override the API endpoint at dev time:

```bash
VITE_API_URL=http://localhost:5000/api/status npm run dev
```

The Svelte app is built with **Svelte 5** and **Vite 8**. It displays the current biodynamic type, weather summary, space-weather Kp index, today's planting suggestion, and any active alerts — refreshing every 5 minutes automatically.

---

## GitHub Pages hosting

This repository includes `.github/workflows/pages.yml` to deploy the Svelte app from `web/dist`.

1. In GitHub repository settings, enable **Pages** with **GitHub Actions** as the source.
2. Add repository variable `KOSMOSTREAM_API_URL` set to your deployed Flask `/api/status` URL.
3. Push to `main` (or run the workflow manually) to publish.

The Svelte site is fully static and reads live data from the configured API URL.

`KOSMOSTREAM_API_URL` should be created as a **Repository variable** under:
**Settings → Secrets and variables → Actions → Variables**.

---

## Routes

| Route | Description |
|---|---|
| `/` | Flask streaming dashboard (full UI) |
| `/api/status` | JSON status endpoint consumed by the Svelte app |
| `/bd-test` | BD icon and moon phase render test page |
