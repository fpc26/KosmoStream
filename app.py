import os
import datetime
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo
from flask import Flask, render_template, jsonify, request, make_response
from db import get_db, init_db
DEFAULT_LAT = 40.0942
DEFAULT_LON = -75.9097
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH")  # Expected path to en_US-ryan-high.onnx
PIPER_BINARY = os.getenv("PIPER_BINARY", "piper")
PIPER_PLAY_CMD = os.getenv("PIPER_PLAY_CMD", "aplay")
PIPER_ENABLED = os.getenv("PIPER_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

# Optional skyfield import for rise/set calculations.
HAS_SKYFIELD = False
try:
    from skyfield import almanac
    from skyfield.api import load, wgs84  # type: ignore

    HAS_SKYFIELD = True
except Exception:
    HAS_SKYFIELD = False



# ---- TTS setup (Piper only) ----
TTS_ENABLED_DEFAULT = os.getenv("TTS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _piper_available():
    if not (PIPER_ENABLED and PIPER_MODEL_PATH):
        return False
    if not shutil.which(PIPER_BINARY):
        return False
    if not shutil.which(PIPER_PLAY_CMD):
        return False
    return True


def _speak_with_piper(text):
    if not text or not _piper_available():
        return False
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp_path = tmp.name
        subprocess.run(
            [PIPER_BINARY, "--model", PIPER_MODEL_PATH, "--output_file", tmp_path],
            input=text.encode("utf-8"),
            check=True,
        )
        subprocess.run([PIPER_PLAY_CMD, tmp_path], check=True)
        return True
    except Exception:
        return False
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def announce(text):
    """Speak text if TTS is enabled and engine is available."""
    if not text:
        return
    _speak_with_piper(text)


def build_suggestion(bd_entry, wx_entry, space_entry):
    """Return a short actionable hint based on BD type, weather POP, heat, and Kp."""
    if not bd_entry:
        return "No BD data yet."

    bd_type = (bd_entry.get("type") or "").lower()
    pop = (wx_entry.get("pop") if wx_entry else None) or 0
    temp_max = (wx_entry.get("temp_max") if wx_entry else None) or None
    kp = (space_entry.get("kp_now") if space_entry else None)

    base_map = {
        "fruit": "Favour fruiting tasks; avoid deep root pruning.",
        "root": "Deep watering and transplant roots; keep foliage handling light.",
        "leaf": "Foliar feed and sow leafy greens; steady moisture helps.",
        "flower": "Support pollinators and light pruning only; good for blooms.",
        "rest": "Rest/maintenance only; skip sowing/planting.",
        "barren": "Rest/maintenance only; skip sowing/planting.",
    }

    tip = base_map.get(bd_type, "Balance tasks to match the day.")

    overlays = []
    if pop >= 0.5:
        overlays.append("Rain likely; defer watering and protect seedlings.")
    if temp_max is not None and temp_max >= 30:
        overlays.append("Heat ahead; avoid midday transplants.")
    if kp is not None and kp >= 5:
        overlays.append("Space weather active (Kp ≥5); expect energetic conditions.")

    if overlays:
        tip = f"{tip} {' '.join(overlays)}"
    return tip


def collect_alerts(bd_entry, wx_entry, space_entry):
    alerts = []
    bd_type = (bd_entry.get("type") if bd_entry else "") or ""
    if bd_type.lower() in {"rest", "barren"}:
        alerts.append({"level": "danger", "text": "BD rest/barren period — avoid sowing/planting."})

    if wx_entry:
        pop = (wx_entry.get("pop") or 0) * 100
        if pop >= 60:
            alerts.append({"level": "warning", "text": f"High rain chance today ({pop:.0f}% POP)."})

    if space_entry and space_entry.get("kp_now") is not None and space_entry["kp_now"] >= 5:
        alerts.append({"level": "warning", "text": f"Space weather alert: Kp {space_entry['kp_now']}."})

    return alerts


def describe_kp(kp_val):
    if kp_val is None:
        return None
    try:
        v = float(kp_val)
    except Exception:
        return None
    if v < 2:
        label = "Quiet"
    elif v < 4:
        label = "Unsettled"
    elif v < 5:
        label = "Active"
    elif v < 7:
        label = "Storm"
    else:
        label = "Severe Storm"
    return f"{label} (Kp {v:g})"


def _clean_note(value):
    """Normalize BD notes: treat lone '-' or empty as None."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "-" or text == "":
        return None
    return text


def _fmt_range(start_dt, end_dt, today_dt):
    """Return a short date range string, labeling today/tomorrow when relevant."""
    def label(d):
        if d == today_dt:
            return "Today"
        if d == today_dt + datetime.timedelta(days=1):
            return "Tomorrow"
        return d.strftime("%b %d")

    if start_dt == end_dt:
        return label(start_dt)
    return f"{label(start_dt)} – {label(end_dt)}"


def build_bd_ranges(rows, today_str):
    """Group contiguous BD days by type, returning up to 33-day planning ranges."""
    if not rows:
        return []
    today_dt = datetime.date.fromisoformat(today_str)
    items = []
    current = None
    for r in rows:
        bd_type = (r.get("type") or "").strip()
        if not bd_type:
            continue
        date_dt = datetime.date.fromisoformat(r["date"])
        phase = r.get("phase", "")
        activities = r.get("activities", "")
        if current and bd_type.lower() == current["type"].lower() and (date_dt - current["end"]).days == 1:
            current["end"] = date_dt
        else:
            if current:
                items.append(current)
            current = {"type": bd_type, "phase": phase, "start": date_dt, "end": date_dt, "activities": activities}
    if current:
        items.append(current)

    # Format for template
    formatted = []
    for it in items:
        formatted.append({
            "type": it["type"],
            "phase": it.get("phase", ""),
            "display_range": _fmt_range(it["start"], it["end"], today_dt),
            "activities": it.get("activities", ""),
        })
    return formatted


def build_phase_list(rows, limit=12):
    """Return upcoming distinct moon phases (new/first/full/last) with first date."""
    wanted = {"new": "New Moon", "first quarter": "First Quarter", "full": "Full Moon", "last quarter": "Last Quarter", "third quarter": "Last Quarter"}
    phases = []
    seen_labels = set()
    for r in rows:
        phase_raw = (r.get("phase") or "").strip()
        phase_l = phase_raw.lower()
        label = None
        for key, name in wanted.items():
            if key in phase_l:
                label = name
                break
        if not label:
            continue
        if label in seen_labels:
            continue
        phases.append({"date": r["date"], "phase": label})
        seen_labels.add(label)
        if len(phases) >= limit:
            break
    return phases


def day_label(date_str, today_str):
    """Return human-friendly labels like Today (Month 18th), Tomorrow, or Weekday with suffix."""
    today = datetime.datetime.fromisoformat(today_str).date()
    target = datetime.datetime.fromisoformat(date_str).date()
    delta = (target - today).days

    def suffix(n):
        if 10 <= n % 100 <= 20:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    pretty_date = target.strftime(f"%B {target.day}{suffix(target.day)}")
    if delta == 0:
        return f"Today ({pretty_date})"
    if delta == 1:
        return f"Tomorrow ({pretty_date})"
    weekday = target.strftime("%A")
    return f"{weekday} {target.day}{suffix(target.day)}" if target.month == today.month else f"{weekday}, {pretty_date}"


def _parse_location(env_name, fallback):
    val = os.getenv(env_name)
    try:
        return float(val) if val is not None else fallback
    except Exception:
        return fallback


def get_location():
    """Return (lat, lon) using env overrides when present."""
    lat = _parse_location("WX_LAT", _parse_location("LAT", DEFAULT_LAT))
    lon = _parse_location("WX_LON", _parse_location("LON", DEFAULT_LON))
    return lat, lon


def get_tzinfo():
    tz_name = os.getenv("ASTRO_TZ")
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    try:
        return datetime.datetime.now().astimezone().tzinfo or datetime.timezone.utc
    except Exception:
        return datetime.timezone.utc


def _format_event(ts_obj, tzinfo):
    if ts_obj is None:
        return None
    local = ts_obj.utc_datetime().replace(tzinfo=datetime.timezone.utc).astimezone(tzinfo)
    return local.strftime("%-I:%M %p")


@lru_cache(maxsize=1)
def _load_ephemeris():
    if not HAS_SKYFIELD:
        return None, None
    try:
        ts = load.timescale()
        eph = load("de421.bsp")
        return ts, eph
    except Exception:
        return None, None


def compute_astro_events(date_str, lat, lon, tzinfo):
    """Return sun/moon rise/set times for a given date and location."""
    if not HAS_SKYFIELD:
        return None
    ts, eph = _load_ephemeris()
    if not ts or not eph:
        return None

    try:
        date = datetime.date.fromisoformat(date_str)
    except ValueError:
        return None

    location = wgs84.latlon(latitude_degrees=lat, longitude_degrees=lon)
    start = ts.utc(date.year, date.month, date.day, 0, 0)
    end = ts.utc(date.year, date.month, date.day, 23, 59)
    events = {"sunrise": None, "sunset": None, "moonrise": None, "moonset": None}

    try:
        sun_times, sun_events = almanac.find_discrete(start, end, almanac.sunrise_sunset(eph, location))
        for t, flag in zip(sun_times, sun_events):
            if flag:
                events["sunrise"] = _format_event(t, tzinfo)
            else:
                events["sunset"] = _format_event(t, tzinfo)
    except Exception:
        pass

    try:
        moon_times, moon_events = almanac.find_discrete(start, end, almanac.risings_and_settings(eph, eph["Moon"], location))
        for t, flag in zip(moon_times, moon_events):
            if flag:
                events["moonrise"] = _format_event(t, tzinfo)
            else:
                events["moonset"] = _format_event(t, tzinfo)
    except Exception:
        pass

    if all(v is None for v in events.values()):
        return None
    return events

app = Flask(__name__)

@app.route("/")
def index():
    # Allow optional ?date=YYYY-MM-DD override for testing/future previews.
    override_date = request.args.get("date")
    today = override_date or datetime.date.today().isoformat()
    lat, lon = get_location()
    tzinfo = get_tzinfo()
    tz_label = datetime.datetime.now(tzinfo).tzname()
    # TTS preference can be overridden via cookie or query param (?tts=on/off)
    tts_param = request.args.get("tts")
    cookie_tts = request.cookies.get("ks_tts")
    if tts_param in {"on", "off"}:
        tts_enabled = tts_param == "on"
    elif cookie_tts in {"on", "off"}:
        tts_enabled = cookie_tts == "on"
    else:
        tts_enabled = TTS_ENABLED_DEFAULT
    conn = get_db()
    bd_row = conn.execute("SELECT * FROM bd_calendar WHERE date=?", (today,)).fetchone()
    wx_row = conn.execute("SELECT * FROM weather_daily WHERE date=?", (today,)).fetchone()
    space_row = conn.execute(
        "SELECT * FROM space_weather ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    forecast_rows = conn.execute(
        "SELECT * FROM weather_daily WHERE date>=? ORDER BY date LIMIT 7", (today,)
    ).fetchall()

    # Wider BD window for planning (22 days)
    bd_window_rows = conn.execute(
        "SELECT * FROM bd_calendar WHERE date>=? ORDER BY date LIMIT 22", (today,)
    ).fetchall()

    bd = dict(bd_row) if bd_row else None
    wx = dict(wx_row) if wx_row else None
    space = dict(space_row) if space_row else None

    # Attach BD + suggestions to forecast rows
    bd_map = {}
    if forecast_rows:
        dates = [row["date"] for row in forecast_rows]
        placeholders = ",".join(["?"] * len(dates))
        bd_rows = conn.execute(
            f"SELECT * FROM bd_calendar WHERE date IN ({placeholders})", tuple(dates)
        ).fetchall()
        bd_map = {row["date"]: dict(row) for row in bd_rows}

    enriched_forecast = []
    for row in forecast_rows:
        wx_entry = dict(row)
        bd_entry = bd_map.get(row["date"])
        if bd_entry:
            bd_entry["notes"] = _clean_note(bd_entry.get("notes"))
        suggestion = build_suggestion(bd_entry, wx_entry, space)
        display_label = day_label(wx_entry["date"], today)
        enriched_forecast.append({"wx": wx_entry, "bd": bd_entry, "suggestion": suggestion, "display_label": display_label})

    if bd:
        bd["notes"] = _clean_note(bd.get("notes"))

    today_suggestion = build_suggestion(bd, wx, space)
    alerts = collect_alerts(bd, wx, space)

    # Gather soundtrack files (static/music/*)
    music_dir = Path("static/music")
    soundtrack = []
    if music_dir.exists():
        for p in sorted(music_dir.iterdir()):
            if p.suffix.lower() in {".mp3", ".wav", ".ogg", ".m4a"}:
                soundtrack.append(p.name)

    # Trigger a concise TTS announcement when enabled.
    summary_parts = []
    if bd:
        summary_parts.append(f"Biodynamic {bd.get('type', '')} day, phase {bd.get('phase', '')}.")
    if wx:
        pop_pct = int(((wx.get("pop") or 0) * 100))
        summary_parts.append(
            f"Weather: {wx.get('description', 'n/a')}, high {wx.get('temp_max', 'n/a')} C, rain chance {pop_pct} percent."
        )
    if space and space.get("kp_now") is not None:
        kp_desc = describe_kp(space.get("kp_now")) or f"Kp {space['kp_now']}"
        summary_parts.append(f"Geomagnetic conditions: {kp_desc}.")
    if today_suggestion:
        summary_parts.append(today_suggestion)
    if tts_enabled:
        announce(" ".join(summary_parts))
    conn.close()
    calendar_days = [dict(r) for r in bd_window_rows]
    bd_ranges = build_bd_ranges(calendar_days, today)
    moon_phases = build_phase_list(calendar_days)

    astro_events = []
    astro_targets = [row["date"] for row in forecast_rows[:3]] if forecast_rows else [today]
    seen_dates = set()
    for date_str in astro_targets:
        if date_str in seen_dates:
            continue
        seen_dates.add(date_str)
        events = compute_astro_events(date_str, lat, lon, tzinfo)
        if events:
            astro_events.append({
                "date": date_str,
                "label": day_label(date_str, today),
                **events,
            })

    resp = make_response(render_template(
        "index.html",
        bd=bd,
        wx=wx,
        space=space,
        forecast=enriched_forecast,
        today_suggestion=today_suggestion,
        alerts=alerts,
        soundtrack=soundtrack,
        current_date=today,
        tts_enabled=tts_enabled,
        day_label=day_label,
        bd_ranges=bd_ranges,
        calendar_days=calendar_days,
        moon_phases=moon_phases,
        astro_events=astro_events,
        astro_tz=tz_label,
    ))
    if tts_param in {"on", "off"}:
        resp.set_cookie("ks_tts", tts_param, max_age=30*24*3600)
    return resp


@app.route("/bd-test")
def bd_test():
    samples = [
        {"type": "Fruit", "phase": "Waxing Gibbous", "activities": "Fruiting tasks"},
        {"type": "Root", "phase": "Waning Gibbous", "activities": "Root crops"},
        {"type": "Leaf", "phase": "Waxing Crescent", "activities": "Leafy greens"},
        {"type": "Flower", "phase": "First Quarter", "activities": "Flowers & blooms"},
        {"type": "Rest", "phase": "Last Quarter", "activities": "Rest day"},
        {"type": "Barren", "phase": "New Moon", "activities": "Rest/avoid planting"},
        {"type": "Other", "phase": "Full Moon", "activities": "Fallback"},
    ]
    return render_template("bd_test.html", samples=samples)

@app.route("/api/status")
def status():
    today = datetime.date.today().isoformat()
    conn = get_db()
    bd_row = conn.execute("SELECT * FROM bd_calendar WHERE date=?", (today,)).fetchone()
    wx_row = conn.execute("SELECT * FROM weather_daily WHERE date=?", (today,)).fetchone()
    space_row = conn.execute(
        "SELECT * FROM space_weather ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    bd = dict(bd_row) if bd_row else None
    wx = dict(wx_row) if wx_row else None
    space = dict(space_row) if space_row else None
    if bd:
        bd["notes"] = _clean_note(bd.get("notes"))

    today_suggestion = build_suggestion(bd, wx, space)
    alerts = collect_alerts(bd, wx, space)
    conn.close()
    return jsonify({
        "bd": bd,
        "weather": wx,
        "space": space,
        "suggestion": today_suggestion,
        "alerts": alerts,
    })

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)