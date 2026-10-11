#!/usr/bin/env python3
"""M10 endpoint checker / M10 rajapintatarkistin.

Usage / Käyttö:
    python test_endpoints.py https://<osoitteesi>.2.rahtiapp.fi
    python test_endpoints.py http://localhost:8080

Valinnainen JSON-tulos (opettajan arviointiskripti) / optional JSON output:
    python test_endpoints.py URL --json

FI: Tarkistin toimii OMAA kantaasi vastaan: se hakee artistin, päivän ja lavan
    tunnisteet rajapinnastasi (/api/artists, /api/days, /api/stages). POST-testin
    lisäämä rivi tarkistetaan hakemalla se takaisin ja poistetaan lopuksi
    DELETE-kutsulla, joten testi ei jätä roskaa ohjelmaan.
EN: The checker works against YOUR OWN database: it reads artist, day and stage
    ids from your API (/api/artists, /api/days, /api/stages). The row inserted by
    the POST test is read back and finally removed with DELETE, so the test leaves
    no junk in the program.
"""
import json
import random
import re
import sys
import urllib.error
import urllib.request

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
JSON_MODE = "--json" in sys.argv
results, log = [], []


def call(base, path, method="GET", body=None):
    """Return (status, parsed_json_or_text, content_type)."""
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, raw, ctype = r.status, r.read().decode(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        status, raw, ctype = e.code, e.read().decode(), e.headers.get("Content-Type", "")
    except Exception as e:  # connection refused, DNS, timeout
        return None, str(e), ""
    try:
        return status, json.loads(raw) if raw else None, ctype
    except json.JSONDecodeError:
        return status, raw, ctype


def check(name, ok, detail=""):
    ok = bool(ok)
    results.append(ok)
    log.append({"check": name.strip(), "ok": ok, "detail": "" if ok else str(detail)[:200]})
    if not JSON_MODE:
        print(f"[{PASS if ok else FAIL}] {name}" + (f"  ({str(detail)[:160]})" if detail and not ok else ""))


def is_list_of_dicts(x):
    return isinstance(x, list) and all(isinstance(i, dict) for i in x)


def first_id(items, key):
    return items[0].get(key) if items and isinstance(items[0], dict) else None


def main(base):
    if not JSON_MODE:
        print(f"Testing {base}\n")

    # 1. Artists
    st, artists, ct = call(base, "/api/artists")
    check("GET /api/artists returns 200", st == 200, f"status={st}")
    check("  Content-Type is application/json", "application/json" in ct, f"Content-Type={ct}")
    check("  response is a non-empty JSON list", is_list_of_dicts(artists) and artists, artists)
    artists = artists if is_list_of_dicts(artists) else []
    check("  items have artist_id and name", artists and {"artist_id", "name"} <= artists[0].keys(),
          f"keys={set(artists[0]) if artists else None}")

    # 2. Days and stages (helper endpoints — ids come from YOUR database)
    st, days, _ = call(base, "/api/days")
    days = days if is_list_of_dicts(days) else []
    check("GET /api/days returns day_id + date", st == 200 and days and {"day_id", "date"} <= days[0].keys(),
          f"status={st}, body={str(days)[:80]}")
    st, stages, _ = call(base, "/api/stages")
    stages = stages if is_list_of_dicts(stages) else []
    check("GET /api/stages returns stage_id + name", st == 200 and stages and {"stage_id", "name"} <= stages[0].keys(),
          f"status={st}, body={str(stages)[:80]}")

    aid, did, sid = first_id(artists, "artist_id"), first_id(days, "day_id"), first_id(stages, "stage_id")
    day_date = first_id(days, "date")

    # 3. One artist's events
    if aid is not None:
        st, ev, _ = call(base, f"/api/artists/{aid}/events")
        check(f"GET /api/artists/{aid}/events returns a JSON list", st == 200 and isinstance(ev, list), f"status={st}")
    st, body, _ = call(base, "/api/artists/999999/events")
    check("GET unknown artist returns 404", st == 404, f"status={st}")

    # 4. Timetable
    st, tt, _ = call(base, "/api/timetable")
    check("GET /api/timetable returns a JSON list", st == 200 and isinstance(tt, list), f"status={st}")
    # FI: suodatustesti käyttää päivää, jolla on ohjelmaa / EN: filter test uses a day that has events
    tt_day = next((r.get("date") for r in tt if isinstance(r, dict) and r.get("date")), day_date) \
        if isinstance(tt, list) else day_date
    if tt_day:
        st, tt, _ = call(base, f"/api/timetable?day={tt_day}")
        tt = tt if is_list_of_dicts(tt) else []
        check(f"GET /api/timetable?day={tt_day} returns only that day",
              st == 200 and tt and all(r.get("date") == tt_day for r in tt),
              f"status={st}, dates={sorted({r.get('date') for r in tt})}")
        starts = [r.get("starts") for r in tt]
        check("  rows are in time order (starts)", starts and None not in starts and starts == sorted(starts),
              f"starts={starts[:5]}")
    st, _, _ = call(base, "/api/timetable?day=not-a-date")
    check("GET timetable with bad date returns 400", st == 400, f"status={st}")

    # 5. POST validation
    st, _, _ = call(base, "/api/events", "POST", {"artist_id": aid})
    check("POST with missing fields returns 400", st == 400, f"status={st}")
    if None in (aid, did, sid, day_date):
        check("POST tests need ids from /api/artists, /api/days and /api/stages", False, "missing ids")
    else:
        # Random small-hours start time: re-runnable despite UNIQUE(day_id, stage_id, start_dt).
        start_dt = f"{day_date} 0{random.randint(0, 4)}:{random.randint(0, 59):02d}:{random.randint(0, 59):02d}"
        st, _, _ = call(base, "/api/events", "POST",
                        {"artist_id": 999999, "stage_id": sid, "day_id": did, "start_dt": start_dt})
        check("POST with bad foreign key returns 400", st == 400, f"status={st}")
        st, _, _ = call(base, "/api/events", "POST",
                        {"artist_id": aid, "stage_id": sid, "day_id": did, "start_dt": "tomorrow at noon"})
        check("POST with bad start_dt format returns 400", st == 400, f"status={st}")

        st, created, _ = call(base, "/api/events", "POST",
                              {"artist_id": aid, "stage_id": sid, "day_id": did, "start_dt": start_dt})
        eid = created.get("event_id") if isinstance(created, dict) else None
        check("POST with valid body returns 201 + event_id", st == 201 and eid is not None,
              f"status={st}, body={str(created)[:120]}")

        # 6. Read-back and clean-up
        if eid is not None:
            _, ev, _ = call(base, f"/api/artists/{aid}/events")
            ids = [r.get("event_id") for r in ev] if is_list_of_dicts(ev) else []
            check("  new event is returned by GET /api/artists/{id}/events", eid in ids, f"event_id={eid}, ids={ids}")
            st, _, _ = call(base, f"/api/events/{eid}", "DELETE")
            check(f"DELETE /api/events/{eid} returns 204", st == 204, f"status={st}")
            _, ev, _ = call(base, f"/api/artists/{aid}/events")
            ids = [r.get("event_id") for r in ev] if is_list_of_dicts(ev) else []
            check("  deleted event is gone", eid not in ids, f"ids={ids}")
            st, _, _ = call(base, f"/api/events/{eid}", "DELETE")
            check("DELETE same event again returns 404", st == 404, f"status={st}")

    if JSON_MODE:
        print(json.dumps({"url": base, "passed": sum(results), "total": len(results), "checks": log}))
    else:
        print(f"\n{sum(results)}/{len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--json"]
    if len(args) != 1 or not re.match(r"^https?://", args[0]):
        print(__doc__)
        sys.exit(2)
    main(args[0])
