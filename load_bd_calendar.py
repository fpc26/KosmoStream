import json
from pathlib import Path
from db import get_db, init_db


def load_calendars():
    """Load all bd_calendar_*.json files and merge entries across years."""
    records = []
    for cal_file in sorted(Path(".").glob("bd_calendar_*.json")):
        payload = json.loads(cal_file.read_text())
        # payload is expected to be {"YYYY": {date: {...}}}
        for year_block in payload.values():
            if isinstance(year_block, dict):
                records.extend(year_block.values())
    return records


def main():
    init_db()
    data = load_calendars()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM bd_calendar")
    cur.executemany(
        """INSERT OR REPLACE INTO bd_calendar
           (date, phase, sign, type, activities, notes)
           VALUES (:date, :phase, :sign, :type, :activities, :notes)""",
        data,
    )
    conn.commit()
    print(f"Loaded {len(data)} days across {len(list(Path('.').glob('bd_calendar_*.json')))} files")
    conn.close()

if __name__ == "__main__":
    main()