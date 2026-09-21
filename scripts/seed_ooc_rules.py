#!/usr/bin/env python3
"""Seed the OOC rulesets — persona traits as data.

Design §11: a persona is a composition of traits (`aloof|mentor|tyrant|general`),
and its ruleset is generated from those traits. `general` is the campaign floor
and every persona carries it; the other traits add their own register rules.

Idempotent: each rule is upserted by id, so re-running refreshes the authored
pattern/delta/layer without touching what the ledger learned about state.

Usage (from rp-engine-py):
    set -a; . /home/maya/.env; set +a
    python3 scripts/seed_ooc_rules.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import Database  # noqa: E402

# (id, trait, kind, layer, pattern, is_regex, delta)
# scope is derived: every rule here is campaign-scope, so session_id stays NULL
# and `ooc_rules_scope_exclusive` holds.
RULES: tuple[tuple[str, str, str, str, str, bool, int], ...] = (
    # ── general — the campaign floor: modern register + first-person emotion ──
    ("gen-modern-slip", "general", "modern_phrasing", "both",
     "re:(okay|ok|hey|guys|stuff|weird)", True, 4),
    ("gen-emotive-apology", "general", "forbidden_lexicon", "both",
     "re:(i am sorry|im sorry|i am fine|im fine)", True, 8),
    ("gen-emotive-love", "general", "forbidden_lexicon", "both",
     "i love you", False, 20),
    ("gen-emotive-need", "general", "forbidden_lexicon", "both",
     "i need you", False, 12),
    # ── aloof — the lockdown persona: the slip is the body, not the words ──
    ("aloof-somatic-falter", "aloof", "somatic_lock", "somatic",
     "re:voice (crack|cracks|breaks|breaking)", True, 6),
    ("aloof-somatic-tears", "aloof", "somatic_lock", "somatic",
     "re:(tears|wept|sobbing|crying)", True, 8),
    ("aloof-warmth-plea", "aloof", "forbidden_lexicon", "both",
     "re:(please stay|stay with me|dont go|don t go)", True, 14),
    # ── mentor — measured, not patronising; no hedged half-orders ──
    ("mentor-patronise", "mentor", "forbidden_lexicon", "both",
     "re:(little one|child|sweetheart|darling)", True, 6),
    ("mentor-hedge", "mentor", "modern_phrasing", "both",
     "re:(maybe|perhaps|i guess|kinda|sorta)", True, 3),
    ("mentor-somatic-doubt", "mentor", "somatic_lock", "somatic",
     "re:(shrugs|shrugged|fidget|fidgets)", True, 5),
    # ── tyrant — commands, never requests; steadiness is the tell ──
    ("tyrant-deference", "tyrant", "forbidden_lexicon", "both",
     "re:(if you dont mind|if you don t mind|sorry to bother)", True, 8),
    ("tyrant-apology", "tyrant", "forbidden_lexicon", "both",
     "re:(my apologies|forgive me)", True, 5),
    ("tyrant-somatic-tremble", "tyrant", "somatic_lock", "somatic",
     "re:(shaking|trembling|quivering)", True, 6),
    # ── tool surface — reaching a tool argument is opt-in: only a rule authored
    #    `tool` sees a tool argument, so a path or identifier cannot trip a
    #    register rule (migration 110 widened the layer check for this). ──
    ("tool-modern-prose", "general", "modern_phrasing", "tool",
     "re:(lol|tbh|gonna|wanna)", True, 2),
)

UPSERT = (
    "INSERT INTO maya_rp.ooc_rules (id, scope, session_id, trait, kind, layer, pattern, is_regex, delta, enabled)"
    " VALUES ($1, 'campaign', NULL, $2, $3, $4, $5, $6, $7, true)"
    " ON CONFLICT (id) DO UPDATE SET trait=EXCLUDED.trait, kind=EXCLUDED.kind, layer=EXCLUDED.layer,"
    " pattern=EXCLUDED.pattern, is_regex=EXCLUDED.is_regex, delta=EXCLUDED.delta, enabled=true"
)


# ── scripted beats (§11): one archetype per trait, proven by prose or action ──
# A beat is paired with rule id `beat:<milestone name>` of kind `scripted_beat`:
# `complete_milestone()` matches that rule to prove the beat happened. Beats are
# never penalties — the engine keeps them out of the deviation audit.
BEATS: tuple[tuple[str, str, str, int, str], ...] = (
    # milestone name, trait, stage, rpp_reward, beat pattern (regex)
    ("aloof-receive-without-answering", "aloof", "lockdown", 5,
     r"re:(says nothing|answers nothing|does not (answer|reply)|in silence)"),
    ("mentor-lay-the-burden", "mentor", "lockdown", 5,
     r"re:(you will (lead|do it)|the burden is yours|your turn to)"),
    ("tyrant-pronounce-punishment", "tyrant", "lockdown", 5,
     r"re:(you are (dismissed|banished|confined)|strip (him|her|them) of)"),
    ("general-order-the-withdrawal", "general", "lockdown", 5,
     r"re:(withdraw|fall back|pull (the|our) (line|fleet) back)"),
)


async def seed_beats() -> tuple[int, int]:
    """Author the scripted beats for every session that has a state row.

    @returns `(milestones, beat_rules)` rows written.
    """
    sessions = await Database.fetch("SELECT session_id FROM maya_rp.ooc_system_state ORDER BY session_id")
    milestones = 0
    rules = 0
    for row in sessions:
        sid = int(row["session_id"])
        for name, trait, stage, reward, pattern in BEATS:
            await Database.execute(
                "INSERT INTO maya_rp.ooc_milestones (session_id, name, trait, stage, rpp_reward)"
                " VALUES ($1,$2,$3,$4,$5)"
                " ON CONFLICT (session_id, name) DO UPDATE SET"
                " trait=EXCLUDED.trait, stage=EXCLUDED.stage, rpp_reward=EXCLUDED.rpp_reward",
                sid, name, trait, stage, reward,
            )
            milestones += 1
            await Database.execute(
                "INSERT INTO maya_rp.ooc_rules"
                " (id, scope, session_id, trait, kind, layer, pattern, is_regex, delta, enabled)"
                " VALUES ($1, 'campaign', NULL, $2, 'scripted_beat', 'both', $3, true, 1, true)"
                " ON CONFLICT (id) DO UPDATE SET"
                " trait=EXCLUDED.trait, kind=EXCLUDED.kind, layer=EXCLUDED.layer,"
                " pattern=EXCLUDED.pattern, is_regex=EXCLUDED.is_regex, enabled=EXCLUDED.enabled",
                f"beat:{name}", trait, pattern,
            )
            rules += 1
    return milestones, rules


async def main() -> int:
    dry = "--dry-run" in sys.argv
    await Database.init()
    if dry:
        print(f"[dry-run] {len(RULES)} rules would be upserted")
        for rule in RULES:
            print(f"  {rule[0]:24s} trait={rule[1]:8s} layer={rule[3]:8s} delta={rule[6]}")
        await Database.close()
        return
    for rule in RULES:
        await Database.execute(UPSERT, *rule)
    beats, beat_rules = await seed_beats()
    print(f"scripted beats: {beats} milestone rows · {beat_rules} beat rules")
    rows = await Database.fetch(
        "SELECT trait, count(*) AS n FROM maya_rp.ooc_rules WHERE scope='campaign' GROUP BY trait ORDER BY trait"
    )
    total = await Database.fetchval("SELECT count(*) FROM maya_rp.ooc_rules")
    print(f"seeded: {len(RULES)} rules · total rows now {total}")
    for row in rows:
        print(f"  trait={row['trait'] or '(campaign)':10s} {row['n']} rules")
    checks = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.ooc_rules WHERE NOT (scope='campaign') = (session_id IS NULL)"
    )
    print(f"scope_exclusive violations: {checks} (expect 0)")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())
