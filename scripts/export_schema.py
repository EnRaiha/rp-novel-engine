#!/usr/bin/env python3
"""Export maya_rp schema (columns, PK, FK, indexes, comments) to Markdown."""
import os, sys
import psycopg2

HOST = os.environ["POSTGRES_HOST"]; PORT = os.environ["POSTGRES_PORT"]
USER = os.environ["POSTGRES_USER"]; DB = os.environ["POSTGRES_DB"]
PW   = os.environ["POSTGRES_PASS"]
SCHEMA = sys.argv[1] if len(sys.argv) > 1 else "maya_rp"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/home/maya/Bumi-Hijau/wiki/rp-dev/schema.md"

conn = psycopg2.connect(host=HOST, port=PORT, user=USER, password=PW, dbname=DB)
conn.autocommit = True
cur = conn.cursor()

def q(sql, args=()):
    cur.execute(sql, args)
    return cur.fetchall()

# ---- tables + comments ----
tables = q("""SELECT c.relname, obj_description(c.oid) FROM pg_class c
   JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname=%s AND c.relkind='r' ORDER BY c.relname""", (SCHEMA,))
tables = [t for t in tables if not t[0].startswith("_")]  # skip internal
tviews = q("""SELECT c.relname, obj_description(c.oid) FROM pg_class c
   JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname=%s AND c.relkind='v' ORDER BY c.relname""", (SCHEMA,))
tseqs = q("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname=%s AND c.relkind='S' ORDER BY c.relname""", (SCHEMA,))

# ---- PK / FK ----
pks = {}
for t, c in q("""SELECT tc.table_name, kcu.column_name FROM information_schema.table_constraints tc
  JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name
  WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=%s""", (SCHEMA,)):
    pks.setdefault(t, []).append(c)

fks = {}
for t, c, ft, fc in q("""SELECT c.conrelid::regclass::text, a.attname, cf.relname, af.attname
  FROM pg_constraint c
  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
  JOIN pg_class cf ON cf.oid = c.confrelid
  JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = ANY(c.confkey)
  WHERE c.contype='f' AND c.connamespace = %s::regnamespace""", (SCHEMA,)):
    t = t.replace(f"{SCHEMA}.", "")
    fks.setdefault(t, []).append((c, ft, fc))

# ---- columns ----
cols = {}
for t, c, dt, cm, np, ns, d, nullable in q("""SELECT table_name, column_name, data_type,
    character_maximum_length, numeric_precision, numeric_scale, column_default, is_nullable
  FROM information_schema.columns WHERE table_schema=%s ORDER BY table_name, ordinal_position""", (SCHEMA,)):
    tname = dt
    if dt in ("character varying", "character"): tname = f"varchar({cm})"
    elif dt == "numeric" and np: tname = f"numeric({np},{ns})"
    elif dt in ("timestamp with time zone",): tname = "timestamptz"
    elif dt in ("timestamp without time zone",): tname = "timestamp"
    cols.setdefault(t, []).append((c, tname, nullable, d))

# ---- indexes ----
idx = {}
for t, i, d in q("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname=%s AND tablename NOT LIKE '\\_%%' ORDER BY tablename, indexname", (SCHEMA,)):
    # compact: keep def, strip schema prefix
    d = d.replace(f"{SCHEMA}.", "")
    idx.setdefault(t, []).append((i, d))

def typ(n):
    n = n.replace(f"{SCHEMA}.", "")
    if n == "vector(768)": return n
    return n

out = []
out.append("# RP Engine Database Schema — `maya_rp`")
out.append("")
out.append(f"*Auto-exported from live PostgreSQL. Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M %Z')}*")
out.append("")
out.append(f"**{len(tables)} tables · {len(tviews)} views · {len(tseqs)} sequences** · database `{DB}` · schema `{SCHEMA}`")
out.append("")
out.append("## Table of Contents")
out.append("")
for t, _ in tables:
    out.append(f"- [[#tbl-{t.lower()}]] {t}")
out.append("")
out.append("## Tables")
out.append("")

for t, comment in tables:
    out.append(f"### tbl-{t.lower()} — `{t}`")
    if comment:
        out.append(f"> [!note] {comment}")
    out.append("")
    out.append("| Column | Type | Null | Default | Key |")
    out.append("|--------|------|:----:|---------|-----|")
    for c, dt, nullable, d in cols.get(t, []):
        key = ""
        if t in pks and c in pks[t]: key = "🔑 PK"
        fk = [f"FK → {ft}.{fc}" for (cc, ft, fc) in fks.get(t, []) if cc == c]
        if fk: key = (key + " · " if key else "") + fk[0]
        if d: d = d.replace(f"{SCHEMA}.", "")
        out.append(f"| `{c}` | {dt} | {'NO' if nullable=='NO' else 'YES'} | {d or '—'} | {key} |")
    if t in idx:
        out.append("")
        out.append("**Indexes:**")
        for i, d in idx[t]:
            out.append(f"- `{i}` — `{d}`")
    out.append("")

out.append("## Views")
out.append("")
for v, comment in tviews:
    out.append(f"### `{v}`")
    if comment: out.append(f"> [!note] {comment}")
    out.append("")
    # view columns
    for c, dt, cm, np, ns, d, nullable in q("""SELECT column_name, data_type, character_maximum_length,
        numeric_precision, numeric_scale, column_default, is_nullable
        FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position""", (SCHEMA, v)):
        tname = dt
        if dt in ("character varying", "character"): tname = f"varchar({cm})"
        elif dt == "numeric" and np: tname = f"numeric({np},{ns})"
        out.append(f"- `{c}` {tname} {'' if nullable=='YES' else '(NOT NULL)'}")
    out.append("")

out.append("## Sequences")
out.append("")
for s in tseqs:
    out.append(f"- `{s}`")

cur.close(); conn.close()
with open(OUT, "w") as f:
    f.write("\n".join(out))
print(f"Schema exported: {OUT} ({len(out)} lines)")
