#!/usr/bin/env python3
"""Roll Theater — makes every roll a story beat (2026-08-14).

• Outcome tiers: FUMBLE / FAIL / PARTIAL ("yes, but") / SUCCESS / CRIT
• Domain flavor tables (deterministic — CPU, zero LLM tokens)
• Queen blessing tokens (Callista/Vera/Aeliana/Rika/Kira)
• Betting pools (Book 08 canon) with roll-history odds
• Hall of legendary rolls (100s and 1s get named + memorialized)
• Consequence ripples: partial/fumble rolls plant seeds (wired)
• Telegram-native dice mapping (dice emoji 1-6 → d100 bands)
"""

from __future__ import annotations
import json, random
from core.db import Database
from core.config import Config
from core.log import info

# ── Outcome tiers (pure) ────────────────────────────────────────────────


def tier_of(total: int, dc: int) -> str:
    """Map (total, dc) → tier. Crits: ≥96 or +30 over DC. Fumbles: ≤5 or -40 under."""
    if total <= 5 or total <= dc - 40:
        return "fumble"
    if total >= 96 or total >= dc + 30:
        return "crit"
    if total < dc - 20:
        return "fail"
    if total < dc:
        return "partial"
    return "success"


TIER_ICONS = {
    "crit": "💥",
    "success": "✅",
    "partial": "🌗",
    "fail": "❌",
    "fumble": "💀",
}

# ── Domain flavor tables (deterministic pick by roll value) ──────────────

FLAVOR = {
    "battle": {
        "crit": [
            "The guns find everything. The enemy formation comes apart like wet paper.",
            "One volley ends it. The enemy flagship turns away, burning.",
        ],
        "fumble": [
            "The targeting grid inverts. Your own escort eats the first salvo.",
            "Formation collapses into friendly fire. Alarms everywhere.",
        ],
        "partial": [
            "You win the exchange, but a cruiser limps home bleeding atmosphere.",
            "Victory — at the cost of a turret line that will never fire again.",
        ],
    },
    "craft": {
        "crit": [
            "The Forge itself would nod. The tolerances are perfect beyond reason.",
            "The piece comes out singing — resonant, balanced, alive.",
        ],
        "fumble": [
            "The alloy fractures mid-cast. Six weeks of work, molten slag.",
            "The blueprint was upside down. The prototype is beautiful garbage.",
        ],
        "partial": [
            "It works — mostly. There's a rattle nobody can find.",
            "Delivered on time, with one weld that will haunt you.",
        ],
    },
    "romance": {
        "crit": [
            "She laughs at the exact right second, and the room is yours.",
            "The words land like a song. Her hand finds yours before you reach.",
        ],
        "fumble": [
            "You call her by the wrong name. The silence has weather.",
            "The gesture misfires — the door, the drink, the moment, all of it.",
        ],
        "partial": [
            "She smiles, but the smile is thinking. You'll be thinking too.",
            "The moment passes — almost. Something to build on, if you're brave.",
        ],
    },
    "diplomacy": {
        "crit": [
            "The envoy forgets her prepared speech and speaks the truth. The room applauds.",
            "Your quiet line lands like a treaty already signed.",
        ],
        "fumble": [
            "The translator unit dies mid-oath. The insult is now permanent.",
            "You offer condolences at a celebration. Nobody forgets.",
        ],
        "partial": [
            "An agreement — with an asterisk the size of a system.",
            "They sign, but the ink stays wet, and the eyes stay narrow.",
        ],
    },
    "travel": {
        "crit": [
            "The thread of space bends kindly. You arrive early, fresh, smug.",
            "Dead reckoning over 40 light-years — and the door opens exactly where promised.",
        ],
        "fumble": [
            "The chart was mirrored. The star you wanted is behind you.",
            "A gravity ripple throws the course — three days lost, one hull plate bowed.",
        ],
        "partial": [
            "You arrive — minus one engine setting and plus one new superstition.",
            "The route works, but the ship complains the whole way.",
        ],
    },
    "social": {
        "crit": [
            "The room reorganizes around you like iron filings.",
            "Your toast lands. Glasses rise in every corner.",
        ],
        "fumble": [
            "You sit in the wrong chair. The wrong chair has a story.",
            "The joke dies at the first table. The second table heard.",
        ],
        "partial": [
            "Half the room is yours; the other half is taking notes.",
            "A good impression — except for the one person who matters.",
        ],
    },
    "mystery": {
        "crit": [
            "The threads knot themselves into a rope. The answer was one drawer away.",
            "You see the pattern everyone walked past for weeks.",
        ],
        "fumble": [
            "The evidence room key was in your other coat. The trail went cold.",
            "You chase the wrong ghost for three days. The real one watched.",
        ],
        "partial": [
            "A lead — thin, and it smells like someone wants you to follow it.",
            "You find half the truth. The other half finds you later.",
        ],
    },
    "pirate": {
        "crit": [
            "The boarders take the ship without a shot. The den speaks your name.",
            "You read the raider's feint before he throws it. The capture is clean.",
        ],
        "fumble": [
            "The grappling hook takes the wrong hull — yours.",
            "You board their ship just as they finish boarding yours.",
        ],
        "partial": [
            "The prize is taken, but the crew now knows how you fight.",
            "You win the boarding — and gain a stowaway with opinions.",
        ],
    },
    "economy": {
        "crit": [
            "The market bends to your ledger. The deal closes before the rivals blink.",
            "You buy the rumor and sell the news. The spread is poetry.",
        ],
        "fumble": [
            "The futures contract matures. So does the mistake.",
            "You signed the wrong page of the right document.",
        ],
        "partial": [
            "Profit — after the tariff, the toll, and the 'handling fee'.",
            "The deal works. The partner now knows your floor.",
        ],
    },
}
DEFAULT_FLAVOR = {
    "crit": ["The dice come down like a falling star. Everything aligns."],
    "fumble": ["The dice laugh. Somewhere, the house records a new low."],
    "partial": ["A half-victory — the kind that keeps its receipt."],
}

# Tiers that no domain table covers (success/fail) used to render as an empty
# string, so the CLI printed blank lines for most rolls.
GENERIC_FLAVOR = {
    "success": [
        "The attempt lands clean. Nothing wasted, nothing spent.",
        "It works. The room moves on, satisfied.",
        "A good outcome, banked without ceremony.",
    ],
    "fail": [
        "The attempt falls short. The cost is paid anyway.",
        "Not this time. The ledger notes the miss.",
        "It slips through the fingers, quietly.",
    ],
    "raw": ["The dice simply report what they are."],
}


def flavor(domain: str, tier: str, total: int) -> str:
    table = (
        FLAVOR.get(domain, DEFAULT_FLAVOR).get(tier)
        or DEFAULT_FLAVOR.get(tier)
        or GENERIC_FLAVOR.get(tier)
        or ["The moment holds."]
    )
    return table[total % len(table)]


# ── Memorials (legendary rolls) ─────────────────────────────────────────

NAMES_CRIT = ["Handshake", "Song", "Beacon", "Signature", "Thread", "Choir", "Dawn"]
NAMES_FUMBLE = ["Laugh", "Oath", "Wound", "Shadow", "Spill", "Toll", "Dusk"]
DOMAIN_WORD = {
    "battle": "the Battlefield",
    "craft": "the Forge",
    "romance": "the Heart",
    "diplomacy": "the Table",
    "travel": "the Stars",
    "social": "the Hall",
    "mystery": "the Dark",
    "pirate": "the Den",
    "economy": "the Ledger",
}


def memorial_name(domain: str, value: int) -> str:
    word = DOMAIN_WORD.get(domain, "the House")
    if value >= 96:
        return f"The {random.choice(NAMES_CRIT)} of {word}"
    return f"The {random.choice(NAMES_FUMBLE)} of {word}"


async def memorialize(
    session_id: int, domain: str, value: int, total: int, dc: int
) -> str:
    """Record a legendary roll (100/1) in roll_hall + events. Returns the name."""
    name = memorial_name(domain, value)
    gd = (
        await Database.fetchval(
            "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id
        )
        or 0
    )
    # local-GPU flavor line, fallback to template (zero DS tokens)
    try:
        from modules.local_gen import generate

        story = await generate(
            f"One epic line (max 20 words) memorializing a legendary {'triumph' if value >= 96 else 'disaster'} "
            f"roll of {value} vs {dc} in domain '{domain}' in a space-opera kingdom. No quotes.",
            max_tokens=40,
            timeout=15.0,
        )
        story = (story or "").strip()
    except Exception as e:
        # local GPU is optional; the template below is the documented fallback.
        info("roll_theater", f"Local flavor line unavailable ({e}), using template")
        story = ""
    if not story:
        story = (
            f"Rolled {value} against {dc} — the {domain} remembers."
            if value >= 96
            else f"Rolled {value} against {dc} — the {domain} will never speak of it."
        )
    await Database.execute(
        "INSERT INTO maya_rp.roll_hall (session_id, roll_name, roll_value, domain, game_day, story) "
        "VALUES ($1,$2,$3,$4,$5,$6)",
        session_id,
        name,
        value,
        domain,
        gd,
        story,
    )
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
        "VALUES ($1, NOW(), 'roll', $2, $3, $4, 4)",
        session_id,
        f"Legendary Roll: {name}",
        f"A {value} was rolled ({domain}) — {story}",
        json.dumps(["roll", domain, "legend"]),
    )
    info("roll_theater", f"Memorialized: {name} ({value})")
    return name


# ── Blessings ───────────────────────────────────────────────────────────


async def list_blessings(session_id: int) -> list[dict]:
    rows = await Database.fetch(
        "SELECT character_name, blessing, effect, charges, last_used_game_day "
        "FROM maya_rp.roll_blessings WHERE session_id=$1 ORDER BY id",
        session_id,
    )
    return [dict(r) for r in rows]


async def consume_blessing(session_id: int, blessing: str) -> bool:
    """Spend one charge (regenerates after 30 game days). Returns success.

    One statement picks the lowest-id usable row and spends it. The outer
    WHERE repeats the usable check, so a concurrent spend of the last charge
    re-checks the new row version and loses instead of spending it twice.
    """
    gd = (
        await Database.fetchval(
            "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id
        )
        or 0
    )
    row = await Database.fetchrow(
        "UPDATE maya_rp.roll_blessings SET charges = CASE WHEN COALESCE(charges, 0) > 0 THEN charges - 1 ELSE 0 END,"
        " last_used_game_day = $3 WHERE id = (SELECT id FROM maya_rp.roll_blessings WHERE session_id=$1 AND blessing=$2"
        " AND (COALESCE(charges, 0) > 0 OR $3 - COALESCE(last_used_game_day, -999) >= 30) ORDER BY id LIMIT 1)"
        " AND (COALESCE(charges, 0) > 0 OR $3 - COALESCE(last_used_game_day, -999) >= 30) RETURNING id",
        session_id,
        blessing,
        gd,
    )
    return row is not None


# ── Betting pools ───────────────────────────────────────────────────────


def pool_odds(crit_rate: float) -> str:
    """Odds from recent crit rate. High crit rate → the house bets against."""
    if crit_rate >= 0.15:
        return "3:1 against the King (the house loves an upset)"
    if crit_rate <= 0.03:
        return "2:1 on the King (the house believes)"
    return "1:1 (even money)"


async def open_pool(session_id: int, name: str, dc: int) -> dict:
    """Open a betting pool on the next vs-roll.

    `dc` is the target the pool is opened for. The pool table carries no dc
    column, so resolution is driven by the caller's `king_won`; dc is checked
    here because a pool opened against a nonsense target is a caller error.
    """
    if not (name or "").strip():
        raise ValueError("open_pool: pool name is empty")
    if int(dc) <= 0:
        raise ValueError(f"open_pool: dc must be positive, got {dc}")
    gd = (
        await Database.fetchval(
            "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id
        )
        or 0
    )
    # crit rate from last 50 rolls (scoped to this session)
    recent = await Database.fetch(
        "SELECT raw_roll, dc FROM maya_rp.roll_history WHERE session_id=$1 ORDER BY id DESC LIMIT 50",
        session_id,
    )
    crits = sum(1 for r in recent if (r["raw_roll"] or 0) >= 96)
    odds = pool_odds(crits / max(1, len(recent)))
    pid = await Database.fetchval(
        "INSERT INTO maya_rp.roll_pools (session_id, pool_name, odds, opened_game_day) "
        "VALUES ($1,$2,$3,$4) RETURNING id",
        session_id,
        name,
        odds,
        gd,
    )
    # simulated bettors: 3 queens + 8 crew, small credits
    crew = await Database.fetch(
        "SELECT name FROM maya_rp.crew_roster WHERE session_id=$1 ORDER BY random() LIMIT 8",
        session_id,
    )
    queens = await Database.fetch(
        "SELECT name FROM maya_rp.characters WHERE session_id=$1 AND is_spouse=true "
        "ORDER BY random() LIMIT 3",
        session_id,
    )
    total_in = 0
    for bettor in list(crew) + list(queens):
        side = random.choice(["king", "house"])
        bet = random.choice([50, 100, 200, 500])
        await Database.execute(
            "INSERT INTO maya_rp.pool_bets (pool_id, bettor_name, bet_credits, bet_side) "
            "VALUES ($1,$2,$3,$4)",
            pid,
            bettor["name"],
            bet,
            side,
        )
        total_in += bet
    await Database.execute(
        "UPDATE maya_rp.roll_pools SET credits_in_pool=$1 WHERE id=$2", total_in, pid
    )
    return {
        "pool_id": pid,
        "name": name,
        "odds": odds,
        "bettors": len(crew) + len(queens),
        "credits_in_pool": total_in,
    }


async def resolve_pool(session_id: int, king_won: bool) -> dict:
    """Close the newest open pool and report the money.

    `house_keeps` is the net the house retains: the pool minus what it paid out.
    An upset pool pays 1.8x on more than it holds, so the net can be negative,
    and the report says so instead of clamping the loss to zero. `crown_credited`
    says whether the crown fee reached a resources row; a fee of 0 is never paid.
    """
    pool = await Database.fetchrow(
        "SELECT id, pool_name, credits_in_pool FROM maya_rp.roll_pools "
        "WHERE session_id=$1 AND status='open' ORDER BY id DESC LIMIT 1",
        session_id,
    )
    if not pool:
        return {"resolved": False}
    # Claim first: a second resolver reads the same open pool and loses here.
    claimed = await Database.fetchrow(
        "UPDATE maya_rp.roll_pools SET result=$1, status='closed' WHERE id=$2 AND status='open' RETURNING id",
        "king" if king_won else "house",
        pool["id"],
    )
    if claimed is None:
        return {"resolved": False}
    bets = await Database.fetch(
        "SELECT id, bettor_name, bet_credits, bet_side FROM maya_rp.pool_bets WHERE pool_id=$1",
        pool["id"],
    )
    house_keeps = 0  # stakes kept off the losers
    paid = 0
    for b in bets:
        won = (b["bet_side"] == "king") == king_won
        payout = int(b["bet_credits"] * 1.8) if won else 0
        house_keeps += b["bet_credits"] if not won else 0
        paid += payout
        if payout:
            await Database.execute(
                "UPDATE maya_rp.pool_bets SET payout=$1 WHERE id=$2", payout, b["id"]
            )
    # Net, not gross: paying 1.8 on the winners can put an upset pool underwater.
    house_keeps = (pool["credits_in_pool"] or 0) - paid
    crown_fee = max(0, house_keeps // 2)
    crown_credited = False
    if king_won and crown_fee:
        row = await Database.fetchrow(
            "UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2 "
            "RETURNING credits",
            crown_fee,
            session_id,
        )
        crown_credited = row is not None
        if not crown_credited:
            info(
                "roll_theater",
                f"Pool {pool['id']}: no resources row for session {session_id}, "
                f"crown fee {crown_fee}C not paid",
            )
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
        "VALUES ($1, NOW(), 'pool', $2, $3, $4, 2)",
        session_id,
        f"Pool closed: {pool['pool_name']}",
        f"The pools paid out — {paid}C to winners, {house_keeps}C to the house.",
        json.dumps(["roll", "pool"]),
    )
    return {
        "resolved": True,
        "pool": pool["pool_name"],
        "paid": paid,
        "house_keeps": house_keeps,
        "crown_fee": crown_fee,
        "crown_credited": crown_credited,
        "winner": "king" if king_won else "house",
    }


# ── Consequence ripples ─────────────────────────────────────────────────


async def plant_ripple(session_id: int, domain: str, tier: str, dc: int) -> None:
    """Partial/fumble rolls plant consequence seeds (wired to consequences.py).

    A success or an unrecognised tier plants nothing and says so on the log.
    """
    if tier not in ("partial", "fumble"):
        info("roll_theater", f"Ripple skipped: tier '{tier}' plants nothing")
        return
    try:
        from core.consequences import plant

        weight = 1 if tier == "partial" else 2
        await plant(
            {
                "session_id": session_id,
                "trigger": f"{domain}_roll_{tier}",
                "cause_description": f"A {tier} roll in {domain} (vs {dc})",
                "effects": [
                    {
                        "type": "stat",
                        # `morale` is not a column of maya_rp.resources. The live
                        # column is aggregate_morale; naming `morale` leaned on
                        # core/consequences.py's unknown-column fallback.
                        "target": "aggregate_morale" if domain != "economy" else "credits",
                        "delta": -weight,
                        # process_due reads a missing delay_ticks as 999 ticks,
                        # so an effect without this one stays planted for good.
                        "delay_ticks": 2,
                    }
                ],
                "can_be_prevented": False,
            }
        )
        info("roll_theater", f"Ripple planted: {domain}/{tier}")
    except Exception as e:
        info("roll_theater", f"Ripple skipped: {e}")


# ── Telegram dice ───────────────────────────────────────────────────────


def parse_telegram_dice(value: int) -> int:
    """Map a Telegram 🎲 result (1-6) to a d100 band.

    1 → 1-5 (fumble territory) · 2 → 6-40 · 3 → 41-60 · 4 → 61-80 ·
    5 → 81-95 · 6 → 96-100 (crit territory). The dice emoji is the entropy, so
    the band is fixed and the same emoji always maps to the same d100. The value
    returned is the band midpoint: 3, 23, 50, 70, 88, 98.
    """
    v = max(1, min(6, int(value)))
    bands = {1: (1, 5), 2: (6, 40), 3: (41, 60), 4: (61, 80), 5: (81, 95), 6: (96, 100)}
    lo, hi = bands[v]
    return (lo + hi) // 2
