import os, requests, datetime
from db import get_db, init_db

LAT = 40.094200
LON = -75.909700
API_KEY = os.environ.get("OWM_API_KEY")
# Default to the 2.5 One Call endpoint (works on the free tier); allow override via env.
ONECALL = os.environ.get("OWM_ONECALL_URL", "https://api.openweathermap.org/data/2.5/onecall")

def main():
    init_db()
    if not API_KEY:
        raise RuntimeError("OWM_API_KEY is not set in environment")
    params = {
        "lat": LAT,
        "lon": LON,
        "appid": API_KEY,
        "units": "metric",
        "exclude": "minutely,hourly,alerts",
    }
    r = requests.get(ONECALL, params=params, timeout=10)
    try:
        r.raise_for_status()
    except requests.HTTPError as exc:
        # Surface a clearer message for common auth issues.
        raise SystemExit(f"Weather fetch failed ({exc}); check OWM_API_KEY and endpoint {ONECALL}")
    daily = r.json().get("daily", [])
    conn = get_db()
    cur = conn.cursor()
    for d in daily:
        date = datetime.datetime.utcfromtimestamp(d["dt"]).strftime("%Y-%m-%d")
        cur.execute(
            """INSERT OR REPLACE INTO weather_daily
               (date, temp_min, temp_max, precipitation, pop, description, icon, moon_phase, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                date,
                d.get("temp", {}).get("min"),
                d.get("temp", {}).get("max"),
                d.get("rain", 0.0),
                d.get("pop", 0.0),
                d.get("weather", [{}])[0].get("description", ""),
                d.get("weather", [{}])[0].get("icon", ""),
                d.get("moon_phase", 0.0),
            ),
        )
    conn.commit()
    conn.close()
    print(f"Stored {len(daily)} daily forecasts")

if __name__ == "__main__":
    main()