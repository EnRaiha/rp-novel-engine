#!/usr/bin/env python3
"""MAP API SERVER — live PG → JSON → galaxy map (no embedded data).

Serves:
  GET /            → galaxy-live.html (renders from fetch, auto-refresh)
  GET /api/map     → all layer data as JSON (live from PostgreSQL)
  GET /api/status  → engine status

Run:  python3 scripts/map_server.py [--port 3460]
"""
import json, re, sys, argparse, os, base64, functools
from flask import Flask, jsonify, send_from_directory, Response, request
import psycopg2

APP = Flask(__name__, static_folder=None)

ASSETS = "/home/maya/Bumi-Hijau/wiki/rp-dev/canon/assets"

# ── Auth config (env or defaults) ──
MAP_USER = os.environ.get("MAP_USER", "maya")
MAP_PASS = os.environ.get("MAP_PASS", "")
API_KEY  = os.environ.get("MAP_API_KEY", "")
AUTH_ENABLED = bool(MAP_PASS) or bool(API_KEY)


def check_auth():
    """Accept either HTTP Basic (user:pass) or ?key= API key."""
    if not AUTH_ENABLED:
        return True
    # API key via header or query
    k = request.headers.get("X-API-Key") or request.args.get("key")
    if API_KEY and k == API_KEY:
        return True
    # Basic auth
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            user, _, pw = decoded.partition(":")
            if user == MAP_USER and pw == MAP_PASS:
                return True
        except Exception:
            pass
    return False


def require_auth(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not check_auth():
            r = jsonify({"error": "unauthorized"})
            r.status_code = 401
            r.headers["WWW-Authenticate"] = 'Basic realm="Map API"'
            return r
        return fn(*args, **kwargs)
    return wrapper


def db():
    """Read-only restricted role: maya_rp schema ONLY (no DML, no other schemas)."""
    return psycopg2.connect(host=os.environ.get("POSTGRES_HOST", "192.168.100.253"),
                            port=int(os.environ.get("POSTGRES_PORT", 5432)),
                            user=os.environ.get("MAP_DB_USER", "map_reader"),
                            dbname=os.environ.get("POSTGRES_DB", "maya_memory"),
                            password=os.environ.get("MAP_DB_PASS", "mapread2026"))

def q(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, r)) for r in cur.fetchall()]

def load_map_data():
    conn = db()
    cur = conn.cursor()
    data = {
        "territories": q(cur, "SELECT id, system_name, controlling_faction, status, population, "
                              "development_level, fleet_presence, contested_by, crisis_level, "
                              "governor_name, economic_output, trade_income FROM maya_rp.territory WHERE session_id=3"),
        "fleets": q(cur, "SELECT f.name, f.formation, COUNT(fm.ship_id) AS ships, "
                         "COALESCE(SUM(s.power_rating),0) AS power FROM maya_rp.fleets f "
                         "LEFT JOIN maya_rp.fleet_members fm ON fm.fleet_id=f.id "
                         "LEFT JOIN maya_rp.ships s ON s.id=fm.ship_id "
                         "WHERE f.session_id=3 AND f.name NOT LIKE 'TKG Defense%' GROUP BY f.id, f.name, f.formation"),
        "zones": q(cur, "SELECT system_id, danger_level FROM maya_rp.pirate_zones WHERE active=true"),
        "megas": q(cur, "SELECT id, current_phase, progress_pct, status, territory_id FROM maya_rp.megastructure_construction WHERE session_id=3"),
        "quests": q(cur, "SELECT id, title, quest_type, status, giver FROM maya_rp.quests WHERE session_id=3 AND status='active'"),
        "arcs": q(cur, "SELECT id, title, theme, phase, status FROM maya_rp.story_arcs WHERE session_id=3 AND status='active'"),
        "chekhov": q(cur, "SELECT id, element_type, description, importance, payoff_deadline, status FROM maya_rp.chekhov_elements WHERE session_id=3 AND status='unpaid'"),
        "seeds": q(cur, "SELECT id, seed_type, content, payoff_game_day, status FROM maya_rp.narrative_seeds WHERE session_id=3 AND status='planted'"),
        "anomalies": q(cur, "SELECT id, anomaly_type, name, studied, data_collected, data_threshold FROM maya_rp.anomalies_catalog WHERE session_id=3"),
        "raids": q(cur, "SELECT id, faction_name, target_system, enemy_power, ticks_remaining, detected FROM maya_rp.incoming_raids WHERE session_id=3 AND player_responded IS NULL"),
        "spies": q(cur, "SELECT faction_id, target_faction_id, agents, effectiveness, active FROM maya_rp.spy_networks WHERE active=true"),
        "ports": q(cur, "SELECT id, territory_id, name, level, status FROM maya_rp.ports WHERE session_id=3"),
        "treaties": q(cur, "SELECT id, name, treaty_type, faction_a_id, faction_b_id, active FROM maya_rp.treaties WHERE active=true"),
        "disasters": q(cur, "SELECT id, name, severity, status, sector_id FROM maya_rp.active_disasters WHERE session_id=3"),
        "trade_routes": q(cur, "SELECT origin_territory_id, destination_territory_id FROM maya_rp.trade_routes WHERE session_id=3 AND active=true"),
        "planets": q(cur, "SELECT id, name, system_name, planet_type, population, max_population, habitability, governor_name, is_capital, territory_id FROM maya_rp.planets WHERE session_id=3 AND population > 0 ORDER BY population DESC"),
        "species": q(cur, "SELECT planet_id, species_name, count, pct, dominant FROM maya_rp.planet_population WHERE session_id=3 AND dominant=TRUE"),
        "sentiment": q(cur, "SELECT territory_id, faction_name, sentiment, approval, fear, trust FROM maya_rp.population_sentiment WHERE session_id=3 ORDER BY sentiment DESC"),
        # ── z-layers (2026-08-14): Upper Veil (z=3) + Lower Veil (z=1) ──
        "veils": {
            "top": q(cur, "SELECT id, name, x_coord, y_coord, z_coord, star_type, controlled_by, hazard_level, hidden FROM maya_rp.sectors WHERE z_coord=3 ORDER BY id"),
            "bottom": q(cur, "SELECT id, name, x_coord, y_coord, z_coord, star_type, controlled_by, hazard_level, hidden FROM maya_rp.sectors WHERE z_coord=1 ORDER BY id"),
        },
        "gates": q(cur, """SELECT a.id AS a_id, a.name AS a_name, a.z_coord AS a_z,
                                  a.x_coord AS a_x, a.y_coord AS a_y,
                                  b.id AS b_id, b.name AS b_name, b.z_coord AS b_z,
                                  b.x_coord AS b_x, b.y_coord AS b_y,
                                  sc.lane_type, sc.distance, sc.travel_time_hours
                           FROM maya_rp.sectors a
                           JOIN maya_rp.sector_connections sc ON sc.from_sector_id=a.id OR sc.to_sector_id=a.id
                           JOIN maya_rp.sectors b ON b.id=CASE WHEN sc.from_sector_id=a.id THEN sc.to_sector_id ELSE sc.from_sector_id END
                           WHERE sc.lane_type IN ('gate','hidden_thread') AND a.id < b.id"""),
        # ── exotic bodies (2026-08-15): wormholes / black holes / white holes ──
        "wormholes": q(cur, """SELECT w.id, w.name, w.stability, w.status, w.discovered,
                                      e.name AS entry_name, e.x_coord AS ex, e.y_coord AS ey,
                                      x.name AS exit_name, x.x_coord AS xx, x.y_coord AS xy
                               FROM maya_rp.wormholes w
                               JOIN maya_rp.sectors e ON e.id = w.entry_sector_id
                               JOIN maya_rp.sectors x ON x.id = w.exit_sector_id
                               WHERE w.session_id=3"""),
        "black_holes": q(cur, """SELECT b.id, b.name, b.hazard_level, b.slingshot_multiplier,
                                        b.time_dilation_ratio, s.name AS sector,
                                        s.x_coord, s.y_coord, s.z_coord
                                 FROM maya_rp.black_holes b
                                 JOIN maya_rp.sectors s ON s.id = b.sector_id
                                 WHERE b.session_id=3"""),
        "white_holes": q(cur, """SELECT w.id, w.name, w.status, w.mystery_pct,
                                        s.name AS sector, s.x_coord, s.y_coord, s.z_coord,
                                        COALESCE(b.name,'—') AS linked_bh
                                 FROM maya_rp.white_holes w
                                 JOIN maya_rp.sectors s ON s.id = w.sector_id
                                 LEFT JOIN maya_rp.black_holes b ON b.id = w.linked_black_hole_id
                                 WHERE w.session_id=3"""),
    }
    # resolve coord lookups
    tid2coord = {}
    for t in data["territories"]:
        m = re.match(r'^-?(\d+)-(-?\d+)$', t["system_name"] or "")
        if m:
            tid2coord[t["id"]] = (int(m.group(1)), int(m.group(2)))
    for z in data["zones"]:
        z["_c"] = tid2coord.get(z["system_id"])
    for m in data["megas"]:
        m["_c"] = tid2coord.get(m["territory_id"])
    for p in data["ports"]:
        p["_c"] = tid2coord.get(p["territory_id"])
    for a in data["anomalies"]:
        a["_c"] = tid2coord.get(a.get("sector_id"))
    conn.close()
    return data

@APP.route("/api/map")
@require_auth
def api_map():
    try:
        data = load_map_data()
        r = Response(json.dumps(data, default=str), mimetype="application/json")
        r.headers["Cache-Control"] = "no-cache"
        return r
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@APP.route("/api/status")
@require_auth
def api_status():
    conn = db(); cur = conn.cursor()
    st = q(cur, "SELECT name, game_day, status FROM maya_rp.sessions WHERE id=3")
    conn.close()
    return jsonify(st[0] if st else {"name": "?"})

@APP.route("/")
@require_auth
def index():
    return send_from_directory(ASSETS, "galaxy-live.html")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3460)
    args = ap.parse_args()
    print(f"MAP API on http://0.0.0.0:{args.port}  (PG → JSON → galaxy map)")
    APP.run(host="0.0.0.0", port=args.port, debug=False)
