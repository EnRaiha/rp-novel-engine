"""scripts/map_server.py: start-up, bind, DSN, XSS, path and write guards.

No database and no live files: `map_server.db` is replaced by a fake connection that records every
statement, and portrait folders live under `tmp_path`. Assertions compare booleans, never a DSN, so a red
run does not print a password.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import runpy
import shutil
import subprocess
import sys

import pytest

from core import portraits as core_portraits

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "map_server.py"
CHARACTERS_HTML = pathlib.Path("/home/maya/Bumi-Hijau/wiki/rp-dev/canon/assets/characters.html")
PAYLOAD = '"></textarea><img src=x onerror=alert(1)>'


# ── harness ─────────────────────────────────────────────────────────────────

class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []

    def execute(self, sql, params=()):
        self.conn.executed.append((sql, params))
        cols, rows = self.conn.handler(sql, params)
        self.description = [(c,) for c in cols]
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(self, handler):
        self.handler = handler
        self.executed = []
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


@pytest.fixture(scope="module")
def map_server():
    spec = importlib.util.spec_from_file_location("map_server_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.APP.config["TESTING"] = True
    return module


@pytest.fixture
def fake_db(map_server, monkeypatch):
    """Install a fake `db()`. Returns the list of connections it handed out."""
    state = {"conns": [], "handler": lambda sql, params: ([], [])}

    def connect():
        conn = FakeConn(lambda sql, params: state["handler"](sql, params))
        state["conns"].append(conn)
        return conn

    monkeypatch.setattr(map_server, "db", connect)
    monkeypatch.setattr(map_server, "AUTH_ENABLED", False)
    return state


@pytest.fixture
def client(map_server, fake_db):
    return map_server.APP.test_client()


@pytest.fixture
def portrait_root(map_server, monkeypatch, tmp_path):
    root = tmp_path / "chars"
    root.mkdir()
    monkeypatch.setattr(core_portraits, "CHARACTERS_ROOT", root)
    monkeypatch.setattr(map_server, "CHARACTERS", str(root))
    return root


def statements(state):
    return [sql for conn in state["conns"] for sql, _ in conn.executed]


# ── (1) import order ────────────────────────────────────────────────────────

def test_script_starts_with_only_its_own_directory_on_the_path(tmp_path):
    """The unit runs the file directly: `sys.path[0]` is `scripts/`, the repo root is absent."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    done = subprocess.run([sys.executable, str(SCRIPT), "--help"], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=60)
    assert "ModuleNotFoundError" not in done.stderr, done.stderr[-400:]
    assert done.returncode == 0, done.stderr[-400:]


# ── (2) portraits ───────────────────────────────────────────────────────────

def test_file_save_reaches_portraits(client, fake_db, portrait_root):
    fake_db["handler"] = lambda sql, params: (["name"], [("Nyx",)])
    reply = client.post("/api/characters/7/file", json={"field": "sheet", "content": "hello"})
    assert reply.status_code == 200
    assert (portrait_root / "nyx" / "sheet.md").read_text(encoding="utf-8") == "hello"


def test_file_save_name_cannot_leave_the_characters_root(client, fake_db, portrait_root):
    fake_db["handler"] = lambda sql, params: (["name"], [("../../evil",)])
    reply = client.post("/api/characters/7/file", json={"field": "sheet", "content": "x"})
    assert reply.status_code == 200
    written = [p for p in portrait_root.parent.rglob("sheet.md")]
    assert written and all(portrait_root in p.parents for p in written)


def test_file_save_refuses_a_field_outside_the_list(client, fake_db, portrait_root):
    reply = client.post("/api/characters/7/file", json={"field": "../../x", "content": "x"})
    assert reply.status_code == 400
    assert not list(portrait_root.rglob("*"))


# ── (3) bind ────────────────────────────────────────────────────────────────

def test_bind_defaults_to_loopback(map_server):
    assert map_server.bind_host({}) == "127.0.0.1"


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "127.0.0.2"])
def test_loopback_bind_needs_no_password(map_server, host):
    assert map_server.bind_host({"MAP_BIND": host}) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "100.64.0.9", "::", "lotus.example"])
def test_non_loopback_bind_is_refused_without_a_password(map_server, host):
    with pytest.raises(SystemExit) as refused:
        map_server.bind_host({"MAP_BIND": host})
    assert "MAP_PASS" in str(refused.value)
    assert host in str(refused.value)


def test_non_loopback_bind_is_allowed_with_a_password(map_server):
    assert map_server.bind_host({"MAP_BIND": "0.0.0.0", "MAP_PASS": "pw"}) == "0.0.0.0"


def _run_main(monkeypatch, env):
    """Run the file as `__main__` with `Flask.run` replaced, so nothing binds. Returns the host handed to it."""
    import flask

    seen = {}
    monkeypatch.setattr(flask.Flask, "run", lambda self, host=None, port=None, **kw: seen.update(host=host, port=port))
    monkeypatch.setattr(sys, "argv", ["map_server.py", "--port", "0"])
    for key in ("MAP_BIND", "MAP_PASS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    runpy.run_path(str(SCRIPT), run_name="__main__")
    return seen.get("host")


def test_main_listens_on_loopback_by_default(monkeypatch):
    assert _run_main(monkeypatch, {}) == "127.0.0.1"


def test_main_honours_the_bind_override_with_a_password(monkeypatch):
    assert _run_main(monkeypatch, {"MAP_BIND": "100.64.0.9", "MAP_PASS": "pw"}) == "100.64.0.9"


def test_main_exits_on_a_public_bind_without_a_password(monkeypatch):
    with pytest.raises(SystemExit):
        _run_main(monkeypatch, {"MAP_BIND": "0.0.0.0"})


# ── (4) DSN ─────────────────────────────────────────────────────────────────

def test_source_carries_no_database_password():
    source = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"mapread\d+", source)
    assert "192.168.100.253" not in source


def test_db_connects_with_the_engine_dsn_read_only(map_server, monkeypatch):
    from urllib.parse import urlsplit

    from core.config import Config

    calls = []

    class Conn:
        def set_session(self, **kw):
            calls.append(("set_session", kw))

    monkeypatch.delenv("MAP_DB_DSN", raising=False)
    monkeypatch.setattr(map_server.psycopg2, "connect", lambda dsn: calls.append(("connect", dsn)) or Conn())
    map_server.db()
    dsn = calls[0][1]
    expected = urlsplit(Config.DSN)
    got = urlsplit(dsn)
    same = ((got.hostname, got.port, got.username, got.password, got.path)
            == (expected.hostname, expected.port, expected.username, expected.password, expected.path))
    assert same
    assert "search_path" not in dsn
    assert calls[1] == ("set_session", {"readonly": True})


def test_map_db_dsn_replaces_the_engine_dsn(map_server):
    dsn = map_server.db_dsn({"MAP_DB_DSN": "postgres://map_reader:pw@db.example:5432/maya_memory?sslmode=require"})
    assert dsn == "postgres://map_reader:pw@db.example:5432/maya_memory?sslmode=require"


# ── (5) XSS and headers ─────────────────────────────────────────────────────

NODE_RUNNER = r"""
const vm = require('vm');
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const written = [];
const els = {};
function makeEl(id) {
  return {
    id, _html: '', textContent: '', dataset: {}, style: {}, disabled: false,
    value: id === 'facet-scope' ? 'all' : id.startsWith('facet-') ? 'any' : '',
    classList: { toggle() {}, add() {}, remove() {} },
    addEventListener() {}, querySelectorAll() { return []; },
    set innerHTML(v) { written.push(String(v)); this._html = String(v); },
    get innerHTML() { return this._html; },
  };
}
const document = {
  getElementById: (id) => (els[id] = els[id] || makeEl(id)),
  querySelectorAll: () => [],
};
async function fetch(path, options) {
  const key = ((options && options.method) || 'GET') + ' ' + path;
  const body = input.routes[key];
  if (body === undefined) return { ok: false, status: 404, json: async () => ({ error: 'no route ' + key }) };
  return { ok: true, status: 200, json: async () => body };
}
const driver = `
;(async () => {
  await new Promise((r) => setImmediate(r));
  await open(1);
  for (const t of ['db', 'sheet', 'fields', 'portraits', 'ooc']) selectTab(t);
})()`;
const ctx = vm.createContext({ document, fetch, console, setImmediate });
vm.runInContext(input.script + driver, ctx)
  .then(() => console.log(JSON.stringify({ written })))
  .catch((e) => { console.error(String(e && e.stack || e)); process.exit(2); });
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_workbench_escapes_every_database_string():
    page = CHARACTERS_HTML.read_text(encoding="utf-8")
    script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    row = {"id": 1, "name": PAYLOAD, "role": PAYLOAD, "archetype": PAYLOAD, "character_type": PAYLOAD,
           "bond": PAYLOAD, "romance_stage": PAYLOAD, "presence": PAYLOAD, "is_spouse": False,
           "beauty_standard": False, "beauty_catalog_id": None, "portraits": PAYLOAD,
           "portraits_pending": PAYLOAD, "portraits_failed": PAYLOAD,
           "appearance_blank": False, "background_blank": False, "species_blank": False}
    editable = ["role", "description", "inventory_jsonb"]
    detail = {
        "character": {"id": 1, "name": PAYLOAD, "role": PAYLOAD, "bond": 5, "romance_stage": PAYLOAD,
                      **{f: PAYLOAD for f in editable}},
        "editable": editable, "slug": PAYLOAD, "folder": PAYLOAD, "folderName": PAYLOAD,
        "files": {f: PAYLOAD for f in ("sheet", "voice", "lore", "intro", "play-guide")},
        "assets": [{"occasion": PAYLOAD, "emotion": PAYLOAD, "status": PAYLOAD, "model": PAYLOAD}],
        "versions": {PAYLOAD: {"versions": [1, 2], "live": 1}},
        "liveFiles": {PAYLOAD: True},
        "suspicion": [{"observer_id": PAYLOAD, "suspicion": PAYLOAD, "last_reason": PAYLOAD, "updated_at": PAYLOAD}],
        "events": [{"happened_at": PAYLOAD, "event_type": PAYLOAD, "importance": PAYLOAD, "title": PAYLOAD}],
    }
    payload = {"script": script, "routes": {"GET /api/characters": [row], "GET /api/characters/1": detail}}
    done = subprocess.run(["node", "-e", NODE_RUNNER], input=json.dumps(payload), capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-600:]
    written = json.loads(done.stdout)["written"]
    assert len(written) >= 5
    joined = "\n".join(written)
    assert "&lt;img src=x onerror=alert(1)&gt;" in joined, "the hostile data never reached innerHTML"
    assert "<img src=x" not in joined


def test_page_defines_the_escape_helper():
    assert "const escapeHtml" in CHARACTERS_HTML.read_text(encoding="utf-8")


def test_every_response_is_nosniff_with_a_csp(client):
    reply = client.get("/api/status")
    assert reply.headers["X-Content-Type-Options"] == "nosniff"
    policy = reply.headers["Content-Security-Policy"]
    assert "default-src 'self'" in policy
    assert "connect-src 'self'" in policy
    assert "object-src 'none'" in policy


def test_unauthorised_and_missing_routes_carry_the_headers_too(map_server, client, monkeypatch):
    monkeypatch.setattr(map_server, "AUTH_ENABLED", True)
    monkeypatch.setattr(map_server, "MAP_PASS", "pw")
    denied = client.get("/api/status")
    assert denied.status_code == 401
    assert denied.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in denied.headers
    missing = client.get("/no-such-route")
    assert missing.status_code == 404
    assert missing.headers["X-Content-Type-Options"] == "nosniff"


def test_workbench_page_runs_script_only_with_its_nonce(client):
    first = client.get("/characters")
    second = client.get("/characters")
    assert first.status_code == 200
    policy = first.headers["Content-Security-Policy"]
    script_src = re.search(r"script-src ([^;]*)", policy).group(1)
    assert "'unsafe-inline'" not in script_src
    nonce = re.search(r"'nonce-([^']+)'", script_src).group(1)
    assert f'<script nonce="{nonce}">' in first.get_data(as_text=True)
    other = re.search(r"'nonce-([^']+)'", second.headers["Content-Security-Policy"]).group(1)
    assert nonce != other


def test_character_files_are_served_sandboxed(client, portrait_root):
    (portrait_root / "nyx").mkdir()
    (portrait_root / "nyx" / "sheet.md").write_text("hi", encoding="utf-8")
    reply = client.get("/characters/nyx/sheet.md")
    assert reply.status_code == 200
    assert reply.headers["Content-Security-Policy"].startswith("sandbox")


# ── (6) character UPDATE ────────────────────────────────────────────────────

def test_character_update_is_a_403_with_no_database_call(client, fake_db):
    reply = client.post("/api/characters/7", json={"role": "spy"})
    assert reply.status_code == 403
    assert reply.is_json
    assert "read-only" in reply.get_json()["error"]
    assert statements(fake_db) == []


def test_character_update_still_needs_auth(map_server, client, monkeypatch):
    monkeypatch.setattr(map_server, "AUTH_ENABLED", True)
    monkeypatch.setattr(map_server, "MAP_PASS", "pw")
    assert client.post("/api/characters/7", json={"role": "spy"}).status_code == 401


def test_no_route_issues_a_write_statement(map_server):
    source = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"\b(UPDATE|INSERT\s+INTO|DELETE\s+FROM)\b\s+maya_rp", source)


# ── (7) path traversal and SQL ──────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/characters/../secret.txt",
    "/characters/%2e%2e/secret.txt",
    "/characters/..%2fsecret.txt",
    "/characters/nyx/../../secret.txt",
    "/characters//etc/passwd",
])
def test_character_files_cannot_be_read_outside_the_root(client, portrait_root, path):
    (portrait_root.parent / "secret.txt").write_text("secret", encoding="utf-8")
    reply = client.get(path)
    assert reply.status_code in (301, 308, 400, 404)
    assert b"secret" not in reply.get_data()


def test_version_promotion_refuses_a_path_in_the_emotion(client, fake_db, portrait_root, tmp_path):
    """`emotion` becomes a file name. A `../` in it moves both the copy source and its target."""
    fake_db["handler"] = lambda sql, params: (["name"], [("Nyx",)])
    (portrait_root / "7-nyx" / "emotions" / "versions").mkdir(parents=True)
    (portrait_root / "out").mkdir()
    (portrait_root / "out" / "x.v1.png").write_bytes(b"png")
    (tmp_path / "out").mkdir()
    reply = client.post("/api/characters/7/version", json={"emotion": "../../../out/x", "version": 1})
    assert reply.status_code == 400
    assert not (tmp_path / "out" / "x.png").exists()
    assert not list(tmp_path.rglob("*.live"))


def test_version_promotion_still_works_for_a_plain_emotion(client, fake_db, portrait_root):
    fake_db["handler"] = lambda sql, params: (["name"], [("Nyx",)])
    versions = portrait_root / "7-nyx" / "emotions" / "versions"
    versions.mkdir(parents=True)
    (versions / "happy.v2.png").write_bytes(b"png")
    reply = client.post("/api/characters/7/version", json={"emotion": "happy", "version": 2})
    assert reply.status_code == 200
    assert (portrait_root / "7-nyx" / "emotions" / "happy.png").read_bytes() == b"png"


@pytest.mark.parametrize("version", ["abc", None, 1e999])
def test_version_promotion_refuses_a_non_integer_version(client, fake_db, portrait_root, version):
    body = '{"emotion": "happy", "version": %s}' % ("Infinity" if version == 1e999 else json.dumps(version))
    reply = client.post("/api/characters/7/version", data=body, content_type="application/json")
    assert reply.status_code == 400


def test_event_search_matches_the_name_literally(map_server, client, fake_db, portrait_root):
    row = {"id": 7, "name": "A_b%c\\d", "session_id": 900}

    def handler(sql, params):
        if "FROM maya_rp.characters WHERE id" in sql:
            return list(row), [tuple(row.values())]
        return [], []

    fake_db["handler"] = handler
    reply = client.get("/api/characters/7")
    assert reply.status_code == 200
    events_sql, events_params = next((s, p) for c in fake_db["conns"] for s, p in c.executed if "maya_rp.events" in s)
    assert "ESCAPE" in events_sql
    assert events_params[1:] == ("%A\\_b\\%c\\\\d%", "%A\\_b\\%c\\\\d%")


def test_trace_limit_falls_back_on_garbage(client, fake_db):
    reply = client.get("/api/ooc/trace?session=900&limit=abc")
    assert reply.status_code == 200
    assert reply.get_json()["session_id"] == 900


def test_every_route_statement_is_a_select(client, fake_db, portrait_root):
    def handler(sql, params):
        if "FROM maya_rp.characters WHERE id" in sql:
            return ["id", "name", "session_id"], [(7, "Nyx", 900)]
        return [], []

    fake_db["handler"] = handler
    for path in ("/api/status", "/api/roster", "/api/characters", "/api/characters/7",
                 "/api/ooc/context?session=900", "/api/ooc/trace?session=900", "/api/map"):
        client.get(path)
    sent = statements(fake_db)
    assert sent
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in sent)
