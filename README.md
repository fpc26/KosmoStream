# KosmoStream

KosmoStream provides:
- A Flask service with biodynamic, weather, and space-weather cards.
- A Svelte web frontend in `./web` for browser-first hosting.

## Local backend run

From the project root:

```bash
export OWM_API_KEY=your_openweather_key
python load_bd_calendar.py
python fetch_weather.py
python fetch_space_weather.py
python app.py
```

The server now performs an automatic once-per-day refresh check so long-running processes reload weather/space/calendar data daily.

If you serve the frontend from a different origin (like GitHub Pages), set:

```bash
export API_CORS_ORIGIN=https://<your-user>.github.io
```

## Svelte web frontend (local)

From `./web`:

```bash
npm install
npm run dev
```

Optional API override:

```bash
VITE_API_URL=http://localhost:5000/api/status npm run dev
```

## GitHub Pages hosting

This repository includes `.github/workflows/pages.yml` to deploy the Svelte app from `web/dist`.

1. In GitHub repository settings, enable **Pages** with **GitHub Actions** as the source.
2. Add repository variable `KOSMOSTREAM_API_URL` set to your deployed API endpoint (for example your hosted Flask `/api/status` URL).
3. Push to `main` (or run the workflow manually) to publish the site.

The Svelte site is static and GitHub Pages-compatible; it reads live status data from the configured API URL.
