import requests
from db import get_db, init_db

Kp_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"


def _parse_kp_row(row):
    """Extract a numeric Kp value from either NOAA row arrays or object records."""
    candidate = None

    if isinstance(row, (list, tuple)):
        # Legacy payload: [time_tag, kp, ...]
        if len(row) > 1:
            candidate = row[1]
    elif isinstance(row, dict):
        # Defensive support for object-based payload variants.
        for key in ("kp", "kp_index", "k_index", "Kp", "Kp_index"):
            if key in row:
                candidate = row[key]
                break

    if candidate in (None, ""):
        return None

    try:
        return float(candidate)
    except (TypeError, ValueError):
        return None

def main():
    init_db()
    r = requests.get(Kp_URL, timeout=10)
    r.raise_for_status()
    payload = r.json()

    # Legacy payload is a JSON array with a header row first; object payloads may omit it.
    if isinstance(payload, list):
        if payload and isinstance(payload[0], list) and payload[0] and str(payload[0][0]).lower() == "time_tag":
            data = payload[1:]
        else:
            data = payload
    else:
        data = []

    recent_rows = data[-8:]  # last 24h (3h cadence)
    kp_values = [kp for kp in (_parse_kp_row(row) for row in recent_rows) if kp is not None]
    kp_now = kp_values[-1] if kp_values else None
    kp_max = max(kp_values) if kp_values else None
    if kp_now is None and kp_max is None:
        summary = "Kp data unavailable"
    else:
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