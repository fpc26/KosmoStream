import os, requests, datetime, collections
from db import get_db, init_db

LAT = 40.094200
LON = -75.909700
API_KEY = os.environ.get("OWM_API_KEY")

# Free tier: use 5-day / 3-hour forecast endpoint and aggregate to daily.
FORECAST_ENDPOINT = os.environ.get("OWM_ENDPOINT", "https://api.openweathermap.org/data/2.5/forecast")

def fetch(endpoint):
    params = {
        "lat": LAT,
        "lon": LON,
        "appid": API_KEY,
        "units": "metric",
    }
    r = requests.get(endpoint, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("list", [])


def aggregate_daily(forecast_list):
    # forecast_list is 3-hourly entries; group by date (local assumed UTC day).
    buckets = collections.defaultdict(list)
    for item in forecast_list:
        dt = datetime.datetime.fromtimestamp(item.get("dt", 0), datetime.timezone.utc)
        day = dt.strftime("%Y-%m-%d")
        buckets[day].append(item)

    daily_rows = []
    for day, items in sorted(buckets.items()):
        temps = [it.get("main", {}).get("temp") for it in items if it.get("main", {}).get("temp") is not None]
        temp_min = min(temps) if temps else None
        temp_max = max(temps) if temps else None

        # Precipitation: sum rain/snow 3h fields
        precip_total = 0.0
        for it in items:
            rain = it.get("rain", {}).get("3h") or 0
            snow = it.get("snow", {}).get("3h") or 0
            precip_total += float(rain) + float(snow)

        # POP: take max
        pops = [it.get("pop") for it in items if it.get("pop") is not None]
        pop_max = max(pops) if pops else 0.0

        # Description/icon: most common
        desc_counter = collections.Counter()
        icon = ""
        for it in items:
            wx = (it.get("weather") or [{}])[0]
            desc = wx.get("description", "")
            icon_val = wx.get("icon", "")
            if desc:
                desc_counter[desc] += 1
                if not icon:
                    icon = icon_val
        description = desc_counter.most_common(1)[0][0] if desc_counter else ""

        daily_rows.append({
            "date": day,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "precipitation": precip_total,
            "pop": pop_max,
            "description": description,
            "icon": icon,
            "moon_phase": None,
        })

    # limit to 7 days max (forecast endpoint gives ~5 days)
    return daily_rows[:7]


def main():
    init_db()
    if not API_KEY:
        raise RuntimeError("OWM_API_KEY is not set in environment")

    forecast_list = fetch(FORECAST_ENDPOINT)
    if not forecast_list:
        raise RuntimeError("No forecast data returned")
    daily = aggregate_daily(forecast_list)
    conn = get_db()
    cur = conn.cursor()
    for d in daily:
        date = d.get("date")
        cur.execute(
            """INSERT OR REPLACE INTO weather_daily
               (date, temp_min, temp_max, precipitation, pop, description, icon, moon_phase, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (
                date,
                d.get("temp_min"),
                d.get("temp_max"),
                d.get("precipitation", 0.0),
                d.get("pop", 0.0),
                d.get("description", ""),
                d.get("icon", ""),
                d.get("moon_phase", 0.0),
            ),
        )
    conn.commit()
    conn.close()
    print(f"Stored {len(daily)} daily forecasts")

if __name__ == "__main__":
    main()