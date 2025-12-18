import json, sqlite3
from pathlib import Path
from db import get_db, init_db

CAL_PATH = Path("bd_calendar_2026.json")

def main():
    init_db()
    data = json.loads(CAL_PATH.read_text())["2026"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM bd_calendar")
    cur.executemany(
        """INSERT OR REPLACE INTO bd_calendar
           (date, phase, sign, type, activities, notes)
           VALUES (:date, :phase, :sign, :type, :activities, :notes)""",
        data.values(),
    )
    conn.commit()
    print(f"Loaded {len(data)} days")
    conn.close()

if __name__ == "__main__":
    main()