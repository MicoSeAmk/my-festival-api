"""My Festival REST API — M10 starter (CSC Rahti).

FI: Tämä on M10-tehtävän lähtöpohja. GET /api/artists on valmiina mallina;
    toteuta loput TODO-kohdat. Aja paikallisesti:  python app.py
    ja testaa:  python test_endpoints.py http://localhost:8080
EN: This is the M10 starter. GET /api/artists is done as an example;
    implement the remaining TODOs. Run locally:  python app.py
    and test:  python test_endpoints.py http://localhost:8080
"""
import os
import sqlite3

from datetime import datetime # lisäys, jota hyödynnetään end_timen laskennassa.
from flask import Flask, jsonify, request

app = Flask(__name__)

# FI: Kanta kulkee kontin mukana. Polun voi vaihtaa ympäristömuuttujalla.
# EN: The database ships inside the container. Override the path with an env var.
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "myfestival.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")  # M8: sqlite3 ei valvo FK:ita oletuksena / FKs are off by default
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/")
def health():
    """FI: Rahti ja selain näkevät, että sovellus on pystyssä.
    EN: Lets Rahti and your browser see the app is up."""
    return jsonify(status="ok", endpoints=["/api/artists", "/api/days", "/api/stages",
                                           "/api/artists/<id>/events", "/api/timetable?day=YYYY-MM-DD",
                                           "POST /api/events", "DELETE /api/events/<id>"])


@app.get("/api/artists")
def get_artists():
    conn = get_db()
    rows = conn.execute("SELECT artist_id, name, country FROM Artist ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.get("/api/days")
def get_days():
    """FI: Apuendpoint: festivaalipäivät (tarkistin hakee tästä day_id:n).
    EN: Helper endpoint: festival days (the checker reads day_id from here).""" # Tähän tehty muutoksia tietokannan muutosten myötä, jotta se toimii päivitetyn kannan kanssa.
    conn = get_db()

    try:
        rows = conn.execute("SELECT day_id, hold_date AS date FROM Day ORDER BY hold_date").fetchall()

        return jsonify([dict(row) for row in rows])

    finally:
        conn.close()


@app.get("/api/stages")
def get_stages():
    """FI: Apuendpoint: lavat. EN: Helper endpoint: stages."""
    conn = get_db()
    rows = conn.execute("SELECT stage_id, name FROM Stage ORDER BY stage_id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.get("/api/artists/<int:artist_id>/events")
def get_artist_events(artist_id):
    conn = get_db()

    try:
        # Onko artisti olemassa?
        artist = conn.execute(
            """
            SELECT artist_id
            FROM Artist
            WHERE artist_id = ?
            """,
            (artist_id,)
        ).fetchone()

        if artist is None:
            return jsonify(error="Artist not found"), 404

        # Haetaan artistin esiintymiset.
        rows = conn.execute(
            """
            SELECT
                e.event_id,
                d.hold_date AS day,
                s.name AS stage,
                e.hit_time AS starts
            FROM Event AS e
            JOIN Day AS d
                ON e.day_id = d.day_id
            JOIN Stage AS s
                ON e.stage_id = s.stage_id
            WHERE e.artist_id = ?
            ORDER BY
                d.hold_date,
                e.hit_time
            """,
            (artist_id,)
        ).fetchall()

        return jsonify([dict(row) for row in rows])

    finally:
        conn.close()


@app.get("/api/timetable")
def get_timetable():
    day = request.args.get("day")

    # Jos day-parametri annettiin, tarkistetaan muoto YYYY-MM-DD.
    if day is not None:
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            return jsonify(
                error="Invalid date. Use format YYYY-MM-DD."
            ), 400

    conn = get_db()

    try:
        sql = """
            SELECT
                d.hold_date AS date,
                s.name AS stage,
                a.name AS artist,
                e.hit_time AS starts,
                time(e.hit_time, '+45 minutes') AS ends
            FROM Event AS e
            JOIN Day AS d
                ON e.day_id = d.day_id
            JOIN Stage AS s
                ON e.stage_id = s.stage_id
            JOIN Artist AS a
                ON e.artist_id = a.artist_id
        """

        parameters = ()

        # Jos päivä annettiin, annetaan vielä parametrisoitu rajaus.
        if day is not None:
            sql += """
                WHERE d.hold_date = ?
            """
            parameters = (day,)

        sql += """
            ORDER BY
                d.hold_date,
                e.hit_time,
                s.name
        """

        rows = conn.execute(sql, parameters).fetchall()

        return jsonify([dict(row) for row in rows])

    finally:
        conn.close()


@app.post("/api/events")
def create_event():
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        return jsonify(error="Request body must be valid JSON."), 400

    required_fields = ["artist_id", "stage_id", "day_id", "start_dt"]
    missing_fields = [
        field
        for field in required_fields
        if field not in body or body[field] is None or body[field] == ""
    ]

    if missing_fields:
        return jsonify(
            error="Missing required fields.",
            missing=missing_fields
        ), 400

    # ID-kenttien tietotyypit.
    try:
        artist_id = int(body["artist_id"])
        stage_id = int(body["stage_id"])
        day_id = int(body["day_id"])
    except (TypeError, ValueError):
        return jsonify(
            error="artist_id, stage_id and day_id must be integers."
        ), 400

    # Hyväksyy esim:
    # 2027-05-09T14:30:00
    # 2027-05-09 14:30:00
    try:
        start_dt = datetime.fromisoformat(str(body["start_dt"]))
    except (TypeError, ValueError):
        return jsonify(
            error="Invalid start_dt. Use ISO format YYYY-MM-DDTHH:MM:SS."
        ), 400

    conn = get_db()

    try:
        # Haetaan festivaalipäivä.
        day_row = conn.execute(
            """
            SELECT day_id, hold_date
            FROM Day
            WHERE day_id = ?
            """,
            (day_id,)
        ).fetchone()

        if day_row is None:
            return jsonify(error="Unknown day_id."), 400

        hold_date = day_row["hold_date"]

        # Aloituspäivän pitää vastata valittua festivaalipäivää.
        if start_dt.date().isoformat() != hold_date:
            return jsonify(
                error="start_dt date does not match day_id.",
                expected_date=hold_date
            ), 400

        # Haetaan esiintymisen tapahtumatyyppi.
        event_type = conn.execute(
            """
            SELECT event_type_id
            FROM EventType
            WHERE type = ?
            """,
            ("Full-Performance",)
        ).fetchone()

        if event_type is None:
            return jsonify(
                error="Full-Performance event type was not found."
            ), 400

        hit_time = start_dt.strftime("%H:%M:%S")

        cursor = conn.execute(
            """
            INSERT INTO Event (
                event_type_id,
                hold_date,
                hit_time,
                day_id,
                stage_id,
                artist_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_type["event_type_id"],
                hold_date,
                hit_time,
                day_id,
                stage_id,
                artist_id
            )
        )

        event_id = cursor.lastrowid
        conn.commit()

        # Hakee lisätyn tapahtuman vastaukseen.
        new_event = conn.execute(
            """
            SELECT
                e.event_id,
                e.artist_id,
                e.stage_id,
                e.day_id,
                d.hold_date AS date,
                e.hit_time AS starts,
                time(e.hit_time, '+45 minutes') AS ends,
                et.type AS event_type
            FROM Event AS e
            JOIN Day AS d
                ON e.day_id = d.day_id
            JOIN EventType AS et
                ON e.event_type_id = et.event_type_id
            WHERE e.event_id = ?
            """,
            (event_id,)
        ).fetchone()

        return jsonify(dict(new_event)), 201

    except sqlite3.IntegrityError as error:
        conn.rollback()

        return jsonify(
            error="Could not create event. Check artist_id, stage_id and day_id.",
            details=str(error)
        ), 400

    finally:
        conn.close()


@app.delete("/api/events/<int:event_id>")
def delete_event(event_id):
    conn = get_db()

    try:
        cursor = conn.execute(
            """
            DELETE FROM Event
            WHERE event_id = ?
            """,
            (event_id,)
        )

        # rowcount == 0 tarkoittaa, ettei kyseistä tapahtumaa löytynyt.
        if cursor.rowcount == 0:
            return jsonify(error="Event not found"), 404

        conn.commit()

        # Onnistunut DELETE palauttaa tyhjän vastauksen.
        return "", 204

    except sqlite3.DatabaseError as error:
        conn.rollback()

        return jsonify(
            error="Could not delete event.",
            details=str(error)
        ), 500

    finally:
        conn.close()


if __name__ == "__main__":
    # FI: Paikallinen kehityspalvelin. Rahdissa sovellusta ajaa gunicorn (ks. Dockerfile).
    # EN: Local dev server. On Rahti the app is run by gunicorn (see Dockerfile).
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
