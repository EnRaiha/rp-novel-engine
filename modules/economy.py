"""Async economy module — tax, population, trade."""
from core.db import Database
from core.utils import calc_game_days, clamp
from datetime import datetime, timezone
from core.log import error

# Progressive marginal tax brackets — PERCENTAGE rates that thin with world size.
# Big worlds still pay more absolute tax (they are huge), but a smaller
# percentage of each marginal population layer. No cliff, no 460x explosion.
#   core (0-10M):         full base rate × dev multiplier (productive core)
#   10M-100M:             18% of base rate
#   100M-1B:              5% of base rate
#   beyond 1B:            0.8% of base rate
BRACKETS = (
    (10_000_000, 1.00),
    (100_000_000, 0.18),
    (1_000_000_000, 0.05),
    (None, 0.008),
)

def _territory_tax(pop, rate, dev_mult, crisis_pen, market_mult: float = 1.0):
    """Marginal bracket tax — returns credits/day for one territory.

    market_mult (2026-08-14): commodity price index feedback — hot markets
    inflate trade-linked tax receipts, cold ones deflate them."""
    rev = 0.0
    remaining = pop
    prev = 0
    for limit, mult in BRACKETS:
        if remaining <= 0:
            break
        if limit is None:
            taxed = remaining
        else:
            taxed = min(remaining, limit - prev)
        # Development bonus applies to the productive core population only.
        dev = dev_mult if mult == 1.0 else 1.0
        rev += taxed * rate * mult * dev * crisis_pen * market_mult
        remaining -= taxed
        prev = limit if limit is not None else prev
    return rev

GATE_TOLL_RATE = 25000            # fair toll per crossing — third parties pay
GATE_TOLL_VOLUME_PER_CROSSING = 40  # units of trade volume = one crossing


async def gate_toll_income(session_id: int = 3) -> int:
    """Foreign-faction gate tolls → Setia treasury (2026-08-15 Izzat canon).

    Setia uses its own gates FREE. Third parties pay the fair toll; income is
    grounded in active trade deals between Setia and non-Setia factions,
    scaled by volume (one crossing per GATE_TOLL_VOLUME_PER_CROSSING units).
    """
    try:
        volume = await Database.fetchval(
            """SELECT COALESCE(SUM(ftd.quantity), 0)
               FROM maya_rp.faction_trade_deals ftd
               JOIN maya_rp.factions fa ON fa.id = ftd.faction_a_id
               JOIN maya_rp.factions fb ON fb.id = ftd.faction_b_id
               WHERE ftd.active
                 AND ftd.session_id = $1
                 AND ((fa.name ILIKE '%Setia%') <> (fb.name ILIKE '%Setia%'))""",
            int(session_id))
    except Exception as e:
        error("economy", f"gate_toll_income: {e}")
        volume = 0
    return (int(volume or 0) // GATE_TOLL_VOLUME_PER_CROSSING) * GATE_TOLL_RATE


async def run_tick(session_id: int = 3):
    row = await Database.fetchrow("SELECT last_tick_at FROM resources WHERE session_id=$1", session_id)
    if not row or not row.get("last_tick_at"):
        return
    gd = calc_game_days(row["last_tick_at"])
    try:
        from modules.market import get_market_index
        _mk = get_market_index(session_id)
        market_mult = 0.9 + 0.2 * min(await _mk, 1.5)
    except Exception:
        market_mult = 1.0
    if gd < 0.01:
        return

    # Get territories
    terr = await Database.fetch(
        "SELECT id, system_name, population, tax_rate, development_level, "
        "crisis_level, max_population, status "
        "FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire'",
        session_id)

    morale = await Database.fetchval(
        "SELECT aggregate_morale FROM resources WHERE session_id=$1", session_id) or 50
    growth_mult = 0.5 + (morale or 50) / 100.0  # morale 50 = baseline, 100 = +50%, 0 = -50%

    total_rev = 0
    total_empire_pop = 0
    global_pop_loss = 0
    refugee_pool = 0
    settlement_targets = []   # (territory_id, spare_capacity) — safe worlds
    pop_events = []

    for t in terr:
        # Dead worlds stay dead — no tax, no growth, no resurrection.
        if t["status"] == "abandoned":
            continue

        pop = t["population"] or 1_000_000
        rate = float(t["tax_rate"] or 0.05)
        dev = t["development_level"] or 1
        crisis = t["crisis_level"] or 0
        crisis_pen = max(0.2, 1 - crisis * 0.05)
        dev_mult = 1 + (dev - 1) * 0.1
        daily = _territory_tax(pop, rate, dev_mult, crisis_pen, market_mult)
        rev = int(daily * gd)
        total_rev += rev

        # ── UNIFIED POPULATION MODEL: grow · migrate · die · wipe ────────

        # 1. CARRYING CAPACITY — max_population override (data-driven),
        #    floored by development so frontier worlds cap at 10M/dev level.
        carrying_cap = max(t["max_population"] or 0, 10_000_000 * dev)

        # 2. NATURAL GROWTH — logistic: strong when small, eases near capacity,
        #    modified by empire morale.
        if pop < carrying_cap:
            growth_potential = 0.02 * gd * (1 - pop / carrying_cap) * growth_mult
            natural_growth = int(pop * max(0.0, growth_potential))
        else:
            natural_growth = 0

        # 3. DEATH / ATTRITION — taxes above 20%, crisis, overpopulation.
        try:
            from modules.ideology import tax_tolerance
            tol = tax_tolerance((await Database.fetchrow(
                "SELECT ideology FROM maya_rp.ideology_state WHERE session_id=$1",
                session_id) or {}).get("ideology", "benevolent_democracy"))
        except Exception:
            tol = 0.20
        tax_death_rate = max(0.0, rate - tol) * 2.0 * gd
        crisis_death_rate = (crisis * 0.01) * gd
        overpop_death_rate = (max(0.0, pop - carrying_cap) / carrying_cap) * 0.005 * gd
        attrition_rate = tax_death_rate + crisis_death_rate + overpop_death_rate
        starvation_death = int(pop * attrition_rate)
        # Minimum death floor — int() truncation makes tiny worlds immortal.
        if starvation_death == 0 and pop > 0 and attrition_rate > 0:
            starvation_death = 1

        # 4. MIGRATION — crisis > 5: 5%/day flee into the refugee pool.
        migration_loss = int(pop * 0.05 * gd) if crisis > 5 else 0
        if migration_loss == 0 and pop > 0 and crisis > 5:
            migration_loss = 1

        net_change = natural_growth - starvation_death - migration_loss
        new_pop = max(0, pop + net_change)
        new_status = t["status"]

        # 5. WIPE — King's rule: anything below 1 resident is a dead world.
        if new_pop < 1:
            new_pop = 0
            new_status = "abandoned"
            pop_events.append(
                f"{t['system_name']} DEPOPULATED — all {int(pop):,} residents dead or fled. Territory abandoned.")

        await Database.execute(
            "UPDATE territory SET population=$1, status=$2, last_population_update=$3 WHERE id=$4",
            new_pop, new_status, datetime.now(timezone.utc).replace(tzinfo=None), t["id"])

        total_empire_pop += new_pop
        global_pop_loss += starvation_death + migration_loss
        refugee_pool += migration_loss

        # Safe worlds with spare capacity become refugee settlement targets.
        if new_pop > 0 and crisis <= 5 and new_pop < carrying_cap:
            settlement_targets.append((t["id"], carrying_cap - new_pop))

    # 6. REFUGEE REDISTRIBUTION — fleeing populations settle in stable worlds,
    #    weighted by spare capacity.
    if refugee_pool > 0 and settlement_targets:
        spare_total = sum(s for _, s in settlement_targets)
        if spare_total > 0:
            placed = 0
            for tid, spare in settlement_targets:
                share = min(spare, int(refugee_pool * spare / spare_total))
                if share <= 0:
                    continue
                await Database.execute(
                    "UPDATE territory SET population=population+$1 WHERE id=$2", share, tid)
                placed += share
            total_empire_pop += placed  # counted where they land
            pop_events.append(
                f"Refugee resettlement: {placed:,} settled into stable worlds.")

    # 7. GLOBAL POOL — sync so collapse.py can trigger the exodus.
    await Database.execute(
        "UPDATE resources SET population=$1 WHERE session_id=$2",
        total_empire_pop, session_id)

    # 8. LOG — population decline / resettlement events.
    if pop_events:
        summary = " | ".join(pop_events[:3])
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, importance) "
            "VALUES ($1, NOW(), 'population', 'Population Report', $2, 3)",
            session_id, summary)

    # Add revenue to resources
    inc_a = int(150_000 * gd)
    inc_f = int(120_000 * gd)
    inc_c = int(200_000 * gd) + total_rev

    # ── GATE TOLL INCOME (2026-08-15 Izzat canon) ──
    # Setia uses its own gates FREE (infrastructure). THIRD PARTIES pay the
    # fair toll (25,000C per crossing). Income = foreign factions' traffic
    # through the gates — grounded in active trade deals with non-Setia
    # factions, scaled by traffic volume.
    toll_income = await gate_toll_income(session_id)
    if toll_income:
        inc_c += toll_income

    await Database.execute(
        "UPDATE resources SET alloys=alloys+$1, fuel=fuel+$2, credits=credits+$3, last_tick_at=$4 WHERE session_id=$5",
        inc_a, inc_f, inc_c, datetime.now(timezone.utc), session_id)

    print(f"  Economy: +{total_rev:,}C tax | +{inc_a:,}A / +{inc_f:,}F / +{inc_c:,}C "
          f"| pop {total_empire_pop:,} (loss {global_pop_loss:,}, refugees {refugee_pool:,})"
          + (f" | gate toll +{toll_income:,}C" if toll_income else ""))


# ─── Action Parser: resolve_intent ───────────────────────────────────────

async def resolve_intent(session_id: int, action: str, target: str, amount: int = 0) -> dict:
    """
    Resolve an economic intent — buy/sell/invest/trade.
    Returns {success, cost, result} for Deepseek narration.
    """
    r = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not r:
        return {"domain": "economy", "success": False, "error": "No resources found"}

    if action == "buy" or action == "purchase":
        if amount <= 0:
            amount = 100_000
        if r["credits"] >= amount:
            await Database.execute(
                "UPDATE maya_rp.resources SET credits = credits - $1 WHERE session_id=$2",
                amount, session_id)
            return {
                "domain": "economy",
                "success": True,
                "cost": amount,
                "credits_remaining": r["credits"] - amount,
                "narrative_hook": f"Purchased {target} for {amount:,} credits.",
            }
        else:
            return {
                "domain": "economy",
                "success": False,
                "cost": amount,
                "credits_available": r["credits"],
                "narrative_hook": f"Insufficient funds for {target}. Need {amount:,}C, have {r['credits']:,}C.",
            }

    elif action == "invest":
        invest_amt = min(amount or 500_000, r["credits"])
        await Database.execute(
            "UPDATE maya_rp.resources SET credits = credits - $1 WHERE session_id=$2",
            invest_amt, session_id)
        return {
            "domain": "economy",
            "success": True,
            "invested": invest_amt,
            "target": target,
            "narrative_hook": f"Invested {invest_amt:,} credits into {target}. Returns expected within the quarter.",
        }

    elif action == "sell" or action == "trade":
        gain = amount if amount > 0 else 200_000
        await Database.execute(
            "UPDATE maya_rp.resources SET credits = credits + $1 WHERE session_id=$2",
            gain, session_id)
        return {
            "domain": "economy",
            "success": True,
            "gain": gain,
            "narrative_hook": f"Completed trade: {target}. Treasury gained {gain:,} credits.",
        }

    return {
        "domain": "economy",
        "success": False,
        "narrative_hook": f"Unknown economic action: {action}. Supported: buy, sell, trade, invest.",
    }
