from flask import Flask, render_template, jsonify
import datetime
from db import get_db, init_db

app = Flask(__name__)

@app.route("/")
def index():
    today = datetime.date.today().isoformat()
    conn = get_db()
    bd = conn.execute("SELECT * FROM bd_calendar WHERE date=?", (today,)).fetchone()
    wx = conn.execute("SELECT * FROM weather_daily WHERE date=?", (today,)).fetchone()
    space = conn.execute(
        "SELECT * FROM space_weather ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    forecast = conn.execute(
        "SELECT * FROM weather_daily WHERE date>=? ORDER BY date LIMIT 7", (today,)
    ).fetchall()
    conn.close()
    return render_template("index.html", bd=bd, wx=wx, space=space, forecast=forecast)

@app.route("/api/status")
def status():
    today = datetime.date.today().isoformat()
    conn = get_db()
    bd = conn.execute("SELECT * FROM bd_calendar WHERE date=?", (today,)).fetchone()
    wx = conn.execute("SELECT * FROM weather_daily WHERE date=?", (today,)).fetchone()
    space = conn.execute(
        "SELECT * FROM space_weather ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return jsonify({
        "bd": dict(bd) if bd else None,
        "weather": dict(wx) if wx else None,
        "space": dict(space) if space else None,
    })

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)