import os
import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from db import get_db, init_db


# ---- TTS setup ----
TTS_ENABLED = os.getenv("TTS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
TTS_VOICE = os.getenv("TTS_VOICE", "male").lower()

tts_engine = None
try:
    import pyttsx3  # type: ignore

    tts_engine = pyttsx3.init()
    if TTS_VOICE == "male":
        # Try to pick a male-ish voice; fallback to default.
        for voice in tts_engine.getProperty("voices"):
            if "male" in voice.name.lower() or "en" in voice.name.lower():
                tts_engine.setProperty("voice", voice.id)
                break
except Exception:
    tts_engine = None  # Degrade gracefully if TTS is unavailable.


def announce(text):
    """Speak text if TTS is enabled and engine is available."""
    if not TTS_ENABLED or not tts_engine or not text:
        return
    try:
        tts_engine.say(text)
        tts_engine.runAndWait()
    except Exception:
        # Silence any runtime TTS failures to avoid breaking the app path.
        pass


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

app = Flask(__name__)

@app.route("/")
def index():
    # Allow optional ?date=YYYY-MM-DD override for testing/future previews.
    override_date = request.args.get("date")
    today = override_date or datetime.date.today().isoformat()
    conn = get_db()
    bd_row = conn.execute("SELECT * FROM bd_calendar WHERE date=?", (today,)).fetchone()
    wx_row = conn.execute("SELECT * FROM weather_daily WHERE date=?", (today,)).fetchone()
    space_row = conn.execute(
        "SELECT * FROM space_weather ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    forecast_rows = conn.execute(
        "SELECT * FROM weather_daily WHERE date>=? ORDER BY date LIMIT 7", (today,)
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
        suggestion = build_suggestion(bd_entry, wx_entry, space)
        enriched_forecast.append({"wx": wx_entry, "bd": bd_entry, "suggestion": suggestion})

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
        summary_parts.append(f"Space weather Kp {space['kp_now']}.")
    if today_suggestion:
        summary_parts.append(today_suggestion)
    announce(" ".join(summary_parts))
    conn.close()
    return render_template(
        "index.html",
        bd=bd,
        wx=wx,
        space=space,
        forecast=enriched_forecast,
        today_suggestion=today_suggestion,
        alerts=alerts,
        soundtrack=soundtrack,
        current_date=today,
    )

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