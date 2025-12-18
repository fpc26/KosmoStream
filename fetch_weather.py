import os, requests, datetime
from db import get_db, init_db

LAT = 40.094200
LON = -75.909700
API_KEY = os.environ.get("OWM_API_KEY", "956ffccafd2e2a2da45744612aa42c4a")
ONECALL = "https://api.openweathermap.org/data/3.0/onecall"

def main():
    init_db()
    params = {
        "lat": LAT,
        "lon": LON,
        "appid": API_KEY,
        "units": "metric",
        "exclude": "minutely,hourly,alerts",
    }
    r = requests.get(ONECALL, params=params, timeout=10)
    r.raise_for_status()
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