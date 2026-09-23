#!/usr/bin/env python3
"""MAP API SERVER — live PG → JSON → galaxy map (no embedded data).

Serves:
  GET /            → galaxy-live.html (renders from fetch, auto-refresh)
  GET /api/map     → all layer data as JSON (live from PostgreSQL)
  GET /api/status  → engine status

Run:  python3 scripts/map_server.py [--port 3460]
"""
import json, re, sys, argparse, os, base64, functools, time
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, Response, request
import psycopg2

APP = Flask(__name__, static_folder=None)

# `core` lives one level up; the unit runs this file directly, so the engine
# package is not on sys.path by default.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

def qp(cur, sql, params=(), one=False):
    """Parameterized companion to `q` for the workbench endpoints."""
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return (rows[0] if rows else None) if one else rows

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

CHARACTERS = "/home/maya/Bumi-Hijau/adventures/tkg/characters"
PLAY_UNIT = "tkg-web"


def _play_url() -> str:
    """The play page's URL.

    The page sits behind the fixed-password proxy (`dsh-auth.service`), so no
    launch token appears here any more; the app's rotating token is injected
    upstream by the proxy.
    """
    return os.environ.get("TKG_PLAY_URL", "https://lotus.tail73711d.ts.net:8443/")


@APP.route("/characters/<path:relpath>")
@require_auth
def characters(relpath):
    return send_from_directory(CHARACTERS, relpath)


@APP.route("/roster")
@require_auth
def roster_page():
    return send_from_directory(ASSETS, "roster.html")


@APP.route("/play")
@require_auth
def play_page():
    return send_from_directory(ASSETS, "tkg-shell.html")


@APP.route("/api/roster")
@require_auth
def api_roster():
    conn = db()
    cur = conn.cursor()
    rows = q(cur, """
        SELECT c.name, c.role, c.bond, COALESCE(c.romance_stage,'') AS stage,
               COALESCE(string_agg(DISTINCT a.occasion, ','), '') AS emotions
        FROM maya_rp.characters c
        LEFT JOIN maya_rp.character_assets a
               ON a.character_id = c.id AND a.status = 'ready'
        WHERE c.session_id = 3 AND c.status IS DISTINCT FROM 'dead'
        GROUP BY c.id, c.name, c.role, c.bond, c.romance_stage
        ORDER BY COALESCE(c.bond,0) DESC, c.id
    """)
    conn.close()
    from core import portraits  # occasion -> the emotion file that was written

    data = []
    for row in rows:
        slug = re.sub(r"[^a-z0-9]+", "-", row["name"].lower()).strip("-")
        emotions = []
        for occasion in (row["emotions"] or "").split(","):
            if not occasion:
                continue
            emotion = portraits.OCCASIONS.get(occasion, (occasion, ()))[0]
            if emotion not in emotions:
                emotions.append(emotion)
        data.append({
            "name": row["name"], "slug": slug, "role": row["role"] or "", "bond": row["bond"] or 0,
            "stage": row["stage"], "emotions": emotions,
        })
    return jsonify(data)


@APP.route("/api/play-url")
@require_auth
def api_play_url():
    return jsonify({"url": _play_url()})




# ── character workbench ─────────────────────────────────────────────────────
# Review and edit one character: the database row (a whitelisted subset), the
# sheet and the four persona-style field files, plus portraits, OOC suspicion
# and the events that mention them. Every file write keeps a timestamped .bak.

CHAR_EDITABLE = (
    "role", "archetype", "character_type", "status", "presence", "scene_location",
    "bond", "bond_level", "romance_flag", "romance_stage", "morality", "is_spouse",
    "importance", "voice_profile", "dialogue_style", "appearance", "description",
    "current_outfit", "species", "house_name", "background", "clearance_level",
    "controlled_by", "relationship_to_player", "last_seen_day", "origin_system",
    "beauty_standard", "dream_essence_affinity", "inventory_jsonb", "wardrobe_jsonb",
    "profile_jsonb",
)
CHAR_FILES = ("sheet", "voice", "lore", "intro", "play-guide")
CHARACTERS_ROOT = Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "characters"
STORY_PATH = Path(os.environ.get("TKG_STORY_PATH", str(CHARACTERS_ROOT.parent / "story.md")))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "unknown"


@APP.route("/nav.js")
@require_auth
def nav_script():
    """The shared navigation rail every page includes."""
    return send_from_directory(ASSETS, "tkg-nav.js", mimetype="application/javascript")


@APP.route("/characters")
@require_auth
def characters_page():
    return send_from_directory(ASSETS, "characters.html")


@APP.route("/api/characters")
@require_auth
def api_characters():
    conn = db()
    cur = conn.cursor()
    rows = q(cur, """
        SELECT c.id, c.name, c.role, c.archetype, c.character_type, c.status, c.presence,
               c.bond, c.romance_stage, c.is_spouse, c.importance, c.species,
               c.beauty_standard, c.beauty_catalog_id,
               (SELECT count(*) FROM maya_rp.character_assets a
                 WHERE a.character_id = c.id AND a.status = 'ready') AS portraits,
               (SELECT count(*) FROM maya_rp.character_assets a
                 WHERE a.character_id = c.id AND a.status = 'pending') AS portraits_pending,
               (SELECT count(*) FROM maya_rp.character_assets a
                 WHERE a.character_id = c.id AND a.status = 'failed') AS portraits_failed,
               (c.appearance IS NULL OR btrim(c.appearance) = '') AS appearance_blank,
               (c.background IS NULL OR btrim(c.background) = '') AS background_blank,
               (c.species IS NULL OR btrim(c.species) = '') AS species_blank
        FROM maya_rp.characters c
        ORDER BY COALESCE(c.bond,0) DESC, c.name
    """)
    conn.close()
    out = []
    for row in rows:
        item = dict(row)
        item["slug"] = _slug(row["name"])
        out.append(item)
    return jsonify(out)


@APP.route("/api/characters/<int:cid>")
@require_auth
def api_character(cid):
    conn = db()
    cur = conn.cursor()
    row = qp(cur, "SELECT * FROM maya_rp.characters WHERE id = %s", (cid,), one=True)
    if row is None:
        conn.close()
        return jsonify({"error": "no such character"}), 404
    name = row["name"]
    from core import portraits

    root = portraits.character_dir(name, cid)
    files = {}
    for field in CHAR_FILES:
        path = root / f"{field}.md"
        files[field] = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

    assets = qp(cur, "SELECT occasion, status, image_path, model, updated_at FROM maya_rp.character_assets"
                     " WHERE character_id=%s ORDER BY occasion", (cid,))
    for asset in assets:
        asset["emotion"] = portraits.OCCASIONS.get(asset["occasion"], (asset["occasion"], ()))[0]
    emotion_keys = sorted({a["emotion"] for a in assets})
    versions = {
        emotion: {"versions": portraits.list_versions(name, emotion, cid),
                  "live": portraits.live_version(name, emotion, cid)}
        for emotion in emotion_keys
    }
    # A frame on disk is shown whether or not its queue row is still pending.
    live_files = {
        emotion: portraits.emotion_path(name, emotion, cid).is_file()
        for emotion in emotion_keys
    }
    suspicion = qp(cur, "SELECT s.observer_id, s.suspicion, s.last_reason, s.updated_at"
                        " FROM maya_rp.ooc_suspicion s WHERE s.session_id = %s AND s.observer_id = %s",
                  (row["session_id"], cid))
    events = qp(cur, "SELECT id, happened_at, event_type, COALESCE(narrative_title, title) AS title, importance"
                     " FROM maya_rp.events WHERE session_id=%s AND (title ILIKE %s OR description ILIKE %s)"
                     " ORDER BY happened_at DESC LIMIT 12",
               (row["session_id"], f"%{name}%", f"%{name}%"))
    conn.close()
    return jsonify({
        "character": dict(row),
        "slug": _slug(name),
        "folder": str(root),
        "folderName": root.name,
        "files": files,
        "assets": [dict(a) for a in assets],
        "versions": versions,
        "liveFiles": live_files,
        "suspicion": [dict(s) for s in suspicion],
        "events": [dict(e) for e in events],
        "editable": list(CHAR_EDITABLE),
    })


@APP.route("/api/characters/<int:cid>", methods=["POST"])
@require_auth
def api_character_update(cid):
    payload = request.get_json(silent=True) or {}
    updates = {k: v for k, v in payload.items() if k in CHAR_EDITABLE}
    if not updates:
        return jsonify({"error": "no editable fields in payload", "editable": list(CHAR_EDITABLE)}), 400
    assignments = ", ".join(f"{col} = %s" for col in updates)
    values = [None if v == "" else v for v in updates.values()]
    conn = db()
    cur = conn.cursor()
    cur.execute(f"UPDATE maya_rp.characters SET {assignments} WHERE id = %s RETURNING id, name", values + [cid])
    updated = cur.fetchone()
    conn.commit()
    conn.close()
    if updated is None:
        return jsonify({"error": "no such character"}), 404
    return jsonify({"ok": True, "id": updated["id"], "fields": list(updates)})


@APP.route("/api/characters/<int:cid>/version", methods=["POST"])
@require_auth
def api_character_version(cid):
    """Make one render version the live image the engine reads."""
    payload = request.get_json(silent=True) or {}
    emotion = str(payload.get("emotion") or "")
    try:
        version = int(payload.get("version"))
    except (TypeError, ValueError):
        return jsonify({"error": "version must be an integer"}), 400
    if not emotion:
        return jsonify({"error": "emotion is required"}), 400
    conn = db()
    cur = conn.cursor()
    row = qp(cur, "SELECT name FROM maya_rp.characters WHERE id = %s", (cid,), one=True)
    conn.close()
    if row is None:
        return jsonify({"error": "no such character"}), 404
    from core import portraits

    try:
        live = portraits.promote_version(row["name"], emotion, version, cid)
    except ValueError as error:
        return jsonify({"error": str(error)}), 404
    return jsonify({"ok": True, "emotion": emotion, "version": version, "live": str(live)})


@APP.route("/api/characters/<int:cid>/file", methods=["POST"])
@require_auth
def api_character_file(cid):
    payload = request.get_json(silent=True) or {}
    field = str(payload.get("field") or "")
    content = payload.get("content")
    if field not in CHAR_FILES:
        return jsonify({"error": f"field must be one of {list(CHAR_FILES)}"}), 400
    if not isinstance(content, str):
        return jsonify({"error": "content must be a string"}), 400
    conn = db()
    cur = conn.cursor()
    row = qp(cur, "SELECT name FROM maya_rp.characters WHERE id = %s", (cid,), one=True)
    conn.close()
    if row is None:
        return jsonify({"error": "no such character"}), 404
    root = portraits.character_dir(row["name"], cid)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{field}.md"
    if path.is_file():
        backup = path.with_suffix(f".md.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    path.write_text(content, encoding="utf-8")
    return jsonify({"ok": True, "field": field, "path": str(path), "bytes": len(content.encode())})


@APP.route("/api/ooc/context")
@require_auth
def api_ooc_context():
    """What the OOC engine holds for a session: stage, gates, suspicion, audits.

    Read-only mirror of the state the harness injects each turn, so the play page
    can show the player why the narrator behaves the way it does.
    """
    sid = int(request.args.get("session") or 3)
    conn = db()
    cur = conn.cursor()
    state = qp(cur, "SELECT arc_stage, deviation, roleplay_points, audits, findings, debuff, updated_at"
                    " FROM maya_rp.ooc_system_state WHERE session_id=%s", (sid,), one=True) or {}
    milestones = qp(cur, "SELECT name, trait, stage, required, rpp_reward, completed_at, expires_at"
                         " FROM maya_rp.ooc_milestones WHERE session_id=%s ORDER BY stage, name", (sid,))
    suspicion = qp(cur, """SELECT c.name, s.suspicion, s.last_reason, s.updated_at
                           FROM maya_rp.ooc_suspicion s
                           JOIN maya_rp.characters c ON c.id = s.observer_id
                           WHERE s.session_id = %s ORDER BY s.suspicion DESC, c.name""", (sid,))
    audits = qp(cur, "SELECT rule_id, layer, disposition, delta, deviation_after, turn_ref, created_at"
                     " FROM maya_rp.ooc_audit_events WHERE session_id=%s ORDER BY id DESC LIMIT 6", (sid,))
    directives = qp(cur, "SELECT id, note, created_at FROM maya_rp.ooc_directives"
                         " WHERE session_id=%s ORDER BY id DESC LIMIT 10", (sid,))
    conn.close()

    stage = str(state.get("arc_stage") or "lockdown")
    arc_file = {"lockdown": "act-1.md", "selective": "act-2.md", "confrontation": "act-3.md"}.get(stage)
    # A session may carry its own brief (`sessions.story_path`), so a restarted arc
    # reads its own story and landmarks from the panel.
    conn = db()
    row = qp(conn.cursor(), "SELECT story_path FROM maya_rp.sessions WHERE id=%s", (sid,), one=True)
    conn.close()
    story_file = Path(row["story_path"]) if row and row.get("story_path") else STORY_PATH
    arc_text = ""
    if arc_file:
        path = story_file.parent / "arcs" / arc_file
        if path.is_file():
            arc_text = path.read_text(encoding="utf-8", errors="replace")
    story = story_file.read_text(encoding="utf-8", errors="replace") if story_file.is_file() else ""
    return jsonify({
        "session_id": sid,
        "stage": stage,
        "state": {key: (str(value) if key == "updated_at" and value else value) for key, value in dict(state).items()},
        "story": story,
        "arc": {"file": arc_file, "text": arc_text, "story_path": str(story_file)},
        "milestones": [dict(row) for row in milestones],
        "suspicion": [dict(row) for row in suspicion],
        "audits": [dict(row) for row in audits],
        "directives": [dict(row) for row in directives],
    })


@APP.route("/api/ooc/trace")
@require_auth
def api_ooc_trace():
    """The engine's own record of the last turns: audits, deltas, beats.

    This is what the narration was actually billed for — the read-out that makes
    the audit visible instead of implied.
    """
    sid = int(request.args.get("session") or 3)
    limit = max(1, min(50, int(request.args.get("limit") or 12)))
    conn = db()
    cur = conn.cursor()
    state = qp(cur, "SELECT arc_stage, deviation, roleplay_points, audits, findings, debuff, updated_at"
                    " FROM maya_rp.ooc_system_state WHERE session_id=%s", (sid,), one=True) or {}
    audits = qp(cur, "SELECT id, rule_id, layer, disposition, skip_reason, delta, deviation_after,"
                     " suspicion_delta, turn_ref, created_at"
                     " FROM maya_rp.ooc_audit_events WHERE session_id=%s ORDER BY id DESC LIMIT %s",
                (sid, limit))
    beats = qp(cur, "SELECT name, trait, stage, rpp_reward, completed_at, expires_at"
                    " FROM maya_rp.ooc_milestones WHERE session_id=%s AND completed_at IS NOT NULL"
                    " ORDER BY completed_at DESC LIMIT 5", (sid,))
    conn.close()
    return jsonify({
        "session_id": sid,
        "state": {key: (str(value) if key == "updated_at" and value else value) for key, value in dict(state).items()},
        "audits": [dict(row) for row in audits],
        "completed_beats": [dict(row) for row in beats],
    })


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
