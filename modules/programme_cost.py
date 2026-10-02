"""Deterministic arithmetic for science programmes and the long knife.

Unit U3, Fasa 2.3 and 2.4. Pure functions only: no database, no files, no
randomness, no seed. Every function returns an exact value a test can assert.

Columns this costs against:

    maya_rp.research_queue   faction_id, tier_target, programme_days,
                             lead_character_id, theory_only
    maya_rp.dark_ops         programme_id, target_character_id,
                             success_chance, outcome
    maya_rp.characters       importance, screened, status
    maya_rp.factions         doctrine

Formulas, written out so a test can check them:

    target_days(tier)          = 1825 * (tier - 4)            programme-days
        1825 = 5 * 365, the King's five years (DECISIONS section 6). One
        programme-day at baseline rate is one research point.

    progress_per_day(lead, lab, doctrine)
                               = 0 when the lead is absent
                               = 1 + min(3, lab) + (1 if doctrine == 'science_tech' else 0)
        Floor 1, ceiling 5. `lab` is a lab level, never research_labs
        .research_rate: the two live rates are 40 and 50, and at 41 a
        1825-day programme finishes in 45 days, which the King's five years
        forbids.

    advance(progress, last_day, game_day, rate, target)
                               = min(target,
                                     progress + rate * max(0, game_day - last_day))
        Idempotent. A second call on the same game_day adds 0.

    target_credits(tier, lab_levels)
                               = 20 * target_days(tier) + 2000 * lab_levels
        20 C per programme-day is ten crew-equivalents at the canon wage of
        2 C per crew-day (modules/fleet_economy.py). 2000 C per lab level is
        tech_tree.build_lab's own price.

    kill_score(step, deniable, screened, importance)
                               = 30 * step + 20 * deniable - 25 * screened
                                 - 15 * (importance >= 5)
    kill_outcome(score)        = 'complete'  if score >= 75
                                 'attempted' if 50 <= score < 75
                                 'failed'    if score < 50

    setback_days(progress, outcome)
                               = min(progress, 1825) if 'complete'
                               = min(progress, 912)  if 'attempted'
                               = 0                   if 'failed'
        1825 programme-days is five years of progress at rate 1. A killed lead
        costs five years, not three. The cap holds progress at or above zero.

    lost_years(setback, rate)  = setback / (rate * 365)

    investigation_score(registered, death_unregistered, outcome)
                               = 20 + 40 * registered
                                    + 20 * death_unregistered
                                    + 20 * (outcome == 'failed')
    case_opens(score)          = score >= 40
    payer_named(score)         = score >= 60

Nothing here reads the world. The caller supplies every flag.
"""

# ─── Calendar and programme shape ───────────────────────────────────
DAYS_PER_YEAR = 365
# 12 months x 30 days + 5 leftover days (D5). modules/calendar_tkg.py still
# computes 360; that bug is tracked in CURRENCY-CALENDAR-2026-10-02.md.

PROGRAMME_BASE_TIER = 4
# The first programme rung is tier 5, so target_days uses tier - 4.

RP_PER_TIER = 5 * DAYS_PER_YEAR
# 1825 programme-days. The King's five years.

MIN_PROGRAMME_TIER = 5
MAX_PROGRAMME_TIER = 9
# 5 is the peak that can be built. 6 to 9 exist only as theory.

# ─── Progress rate ──────────────────────────────────────────────────
LAB_LEVEL_CAP = 3
DOCTRINE_BONUS = 1
# 1 for the lead, up to 3 for lab levels, 1 for science_tech doctrine.
# Floor 1, ceiling 5 programme-days per game-day.

# ─── Credit ─────────────────────────────────────────────────────────
LEAD_UPKEEP_CREDITS_PER_DAY = 20
# Ten crew-equivalents at the canon wage of 2 C per crew-day.
LAB_LEVEL_CREDITS = 2000
# tech_tree.build_lab charges 2000 C per lab.

# ─── The knife ──────────────────────────────────────────────────────
ASSASSINATION_STEP_CREDITS = 5000
# dark_ops.OP_COSTS['assassinate'] prices 5000 C. Step 1 is that price.
MIN_SPEND_STEP = 1
MAX_SPEND_STEP = 3

KILL_STEP_WEIGHT = 30
KILL_DENIABLE_BONUS = 20
# Deniable means sponsor_faction_id IS NULL: no name on the ledger.
GUARD_SCREENED_WEIGHT = 25
GUARD_IMPORTANCE_WEIGHT = 15
GUARD_IMPORTANCE_AT = 5
KILL_COMPLETE_AT = 75
KILL_ATTEMPTED_AT = 50

SETBACK_DAYS_COMPLETE = RP_PER_TIER
# 1825 programme-days, five years. Not three.
SETBACK_DAYS_ATTEMPTED = RP_PER_TIER // 2
# 912 programme-days, a wound.

# ─── The investigation ──────────────────────────────────────────────
INVESTIGATION_BASE = 20
INVESTIGATION_REGISTERED_WEIGHT = 40
INVESTIGATION_UNREGISTERED_DEATH_WEIGHT = 20
INVESTIGATION_FAILED_KILL_WEIGHT = 20
INVESTIGATION_OPEN_AT = 40
INVESTIGATION_PAYER_AT = 60

KILL_OUTCOMES = ("complete", "attempted", "failed")


def target_days(tier_target: int) -> int:
    """Programme-days needed to finish a tier. Tier 5 is 1825, tier 7 is 5475."""
    if tier_target < MIN_PROGRAMME_TIER or tier_target > MAX_PROGRAMME_TIER:
        raise ValueError(
            f"tier_target {tier_target} is outside "
            f"{MIN_PROGRAMME_TIER}..{MAX_PROGRAMME_TIER}"
        )
    return RP_PER_TIER * (tier_target - PROGRAMME_BASE_TIER)


def progress_per_day(lead_present: bool, lab_level: int, doctrine: str) -> int:
    """Programme-days added per game-day. Zero without a named lead."""
    if not lead_present:
        return 0
    lab = max(0, min(LAB_LEVEL_CAP, int(lab_level)))
    bonus = DOCTRINE_BONUS if doctrine == "science_tech" else 0
    return 1 + lab + bonus


def advance(
    progress_days: int,
    last_progress_day: int,
    game_day: int,
    rate: int,
    target: int,
) -> int:
    """New programme_days after a tick. Same game_day twice adds nothing."""
    elapsed = max(0, game_day - last_progress_day)
    if rate <= 0:
        return max(0, min(progress_days, target))
    return max(0, min(target, progress_days + rate * elapsed))


def target_credits(tier_target: int, lab_levels: int = LAB_LEVEL_CAP) -> int:
    """Credit to fund a programme from zero: lead upkeep plus lab plant."""
    if lab_levels < 0:
        raise ValueError("lab_levels cannot be negative")
    return (
        LEAD_UPKEEP_CREDITS_PER_DAY * target_days(tier_target)
        + LAB_LEVEL_CREDITS * lab_levels
    )


def kill_score(
    spend_step: int,
    deniable: bool,
    screened: bool,
    importance: int,
) -> int:
    """Deterministic kill score. Same row in, same score out. No dice."""
    if spend_step < MIN_SPEND_STEP or spend_step > MAX_SPEND_STEP:
        raise ValueError(f"spend_step {spend_step} is outside 1..3")
    score = KILL_STEP_WEIGHT * spend_step
    if deniable:
        score += KILL_DENIABLE_BONUS
    if screened:
        score -= GUARD_SCREENED_WEIGHT
    if importance >= GUARD_IMPORTANCE_AT:
        score -= GUARD_IMPORTANCE_WEIGHT
    return score


def kill_outcome(score: int) -> str:
    """Read a kill score as one of complete, attempted, failed."""
    if score >= KILL_COMPLETE_AT:
        return "complete"
    if score >= KILL_ATTEMPTED_AT:
        return "attempted"
    return "failed"


def setback_days(progress_days: int, outcome: str) -> int:
    """Programme-days lost. A killed lead costs 1825, which is five years."""
    if outcome not in KILL_OUTCOMES:
        raise ValueError(f"outcome must be one of {KILL_OUTCOMES}")
    if progress_days < 0:
        raise ValueError("progress_days cannot be negative")
    if outcome == "complete":
        return min(progress_days, SETBACK_DAYS_COMPLETE)
    if outcome == "attempted":
        return min(progress_days, SETBACK_DAYS_ATTEMPTED)
    return 0


def lost_years(setback: int, rate: int) -> float:
    """Wall-clock years the programme loses. A stalled programme loses none."""
    if rate <= 0:
        return 0.0
    return setback / (rate * DAYS_PER_YEAR)


def investigation_score(
    registered: bool,
    death_unregistered: bool,
    outcome: str,
) -> int:
    """How provable the case is, from the money that bought the kill."""
    if outcome not in KILL_OUTCOMES:
        raise ValueError(f"outcome must be one of {KILL_OUTCOMES}")
    score = INVESTIGATION_BASE
    if registered:
        score += INVESTIGATION_REGISTERED_WEIGHT
    if death_unregistered:
        score += INVESTIGATION_UNREGISTERED_DEATH_WEIGHT
    if outcome == "failed":
        score += INVESTIGATION_FAILED_KILL_WEIGHT
    return score


def case_opens(score: int) -> bool:
    """True when the score is enough to file an investigation."""
    return score >= INVESTIGATION_OPEN_AT


def payer_named(score: int) -> bool:
    """True when the payer is a registry fact, which pulls the case to Panel."""
    return score >= INVESTIGATION_PAYER_AT
