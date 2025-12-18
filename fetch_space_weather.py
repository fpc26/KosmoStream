import requests
from db import get_db, init_db

Kp_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

def main():
    init_db()
    r = requests.get(Kp_URL, timeout=10)
    r.raise_for_status()
    data = r.json()[1:]  # skip header
    kp_values = [float(row[1]) for row in data[-8:]]  # last 24h (3h cadence)
    kp_now = kp_values[-1] if kp_values else None
    kp_max = max(kp_values) if kp_values else None
    summary = f"Kp now {kp_now}, 24h max {kp_max}"
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO space_weather (fetched_at, kp_now, kp_24h_max, summary)
           VALUES (datetime('now'), ?, ?, ?)""",
        (kp_now, kp_max, summary),
    )
    conn.commit()
    conn.close()
    print(summary)

if __name__ == "__main__":
    main()