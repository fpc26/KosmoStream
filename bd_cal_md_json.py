import json, re
from pathlib import Path

SRC = Path("2026_grok_BD_cal.md")
OUT = Path("bd_calendar_2026.json")

def parse_md_table(md: str):
    # Split by month headers (lines that start with ### <Month>)
    entries = {}
    month_blocks = re.split(r"^###\s+", md, flags=re.MULTILINE)
    for block in month_blocks:
        if not block.strip():
            continue
        lines = block.strip().splitlines()
        month_name = lines[0].strip()
        table_lines = [ln for ln in lines[1:] if ln.strip() and not ln.strip().startswith("|----")]
        headers = []
        rows = []
        for ln in table_lines:
            if ln.startswith("| Date"):
                headers = [h.strip() for h in ln.strip("|").split("|")]
                continue
            if not headers:
                continue
            cols = [c.strip() for c in ln.strip("|").split("|")]
            if len(cols) != len(headers):
                continue
            row = dict(zip(headers, cols))
            rows.append(row)
        for row in rows:
            day = row.get("Date")
            # Normalize date to YYYY-MM-DD
            mon = month_name.split()[0][:3]  # e.g., Jan
            year = "2026"
            mon_num = {
                "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
            }[mon]
            day_num = f"{int(day.split()[1]):02d}" if " " in day else f"{int(day):02d}"
            iso_date = f"{year}-{mon_num}-{day_num}"
            entries[iso_date] = {
                "date": iso_date,
                "phase": row.get("Phase", ""),
                "sign": row.get("Sign (Transit)", ""),
                "type": row.get("Type", ""),
                "activities": row.get("Activities", ""),
                "notes": row.get("Notes", "")
            }
    return entries

def main():
    md = SRC.read_text(encoding="utf-8")
    data = parse_md_table(md)
    OUT.write_text(json.dumps({"2026": data}, indent=2), encoding="utf-8")
    print(f"Wrote {len(data)} days to {OUT}")

if __name__ == "__main__":
    main()
