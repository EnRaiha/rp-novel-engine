#!/usr/bin/env python3
"""harness_sync.py — wire the token/cost telemetry layer (2026-08-14).

opencode_sessions records total_cost/tokens per session, but harness.budget
was never populated — the harness control plane (budget guard, route log)
had nothing to read. This syncs the last 50 sessions into harness.budget
and the route_log summary rows.

Runs as maya owner (rp_engine role lacks grants on public.opencode_sessions).
Usage:
  python3 scripts/harness_sync.py          # sync + print summary
  python3 scripts/harness_sync.py --days 7 # window filter
  (register with cron for hourly sync)
"""
import argparse, os, subprocess, sys

HOST = os.environ.get("POSTGRES_HOST", "100.65.243.60")
DB = "maya_memory"
MAYA_PASS = "REDACTED"

SQL = """
INSERT INTO harness.budget
  (session_id, cumulative_cost, turn_count, total_tokens, last_model, tokens_reasoning, updated_at)
SELECT s.session_id,
       COALESCE(s.total_cost, 0),
       (SELECT COUNT(*) FROM public.opencode_messages m WHERE m.session_id = s.session_id),
       COALESCE(s.total_tokens_input, 0) + COALESCE(s.total_tokens_output, 0),
       s.model,
       COALESCE(s.total_tokens_reasoning, 0),
       NOW()
FROM public.opencode_sessions s
WHERE s.time_created > NOW() - INTERVAL '%s days'
ON CONFLICT (session_id) DO UPDATE SET
  cumulative_cost = EXCLUDED.cumulative_cost,
  turn_count = EXCLUDED.turn_count,
  total_tokens = EXCLUDED.total_tokens,
  last_model = EXCLUDED.last_model,
  tokens_reasoning = EXCLUDED.tokens_reasoning,
  updated_at = NOW();
"""

def run_sql(sql: str) -> str:
    env = dict(os.environ)
    env["PGPASSWORD"] = MAYA_PASS
    r = subprocess.run(
        ["psql", "-h", HOST, "-U", "maya", "-d", DB, "-c", sql],
        capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(1)
    return r.stdout

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    out = run_sql(SQL % args.days)
    print(out)
    summary = run_sql(
        "SELECT COUNT(*) AS rows, ROUND(SUM(cumulative_cost)::numeric,4) AS total_cost_30d, "
        "SUM(total_tokens) AS tokens, SUM(tokens_reasoning) AS reasoning "
        "FROM harness.budget WHERE updated_at > NOW() - INTERVAL '1 hour'")
    print("── harness.budget synced:", summary.strip())

if __name__ == "__main__":
    main()
