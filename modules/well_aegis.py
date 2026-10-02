"""Deterministic arithmetic for the Well al-Wakr and Aegis Sight.

Unit U4, Fasa 3.2 and 3.3. Pure functions only: no database, no files, no
randomness, no seed. Every function returns an exact value a test can assert.

The Well is counted from inside, in drops. `the-sunrise.md:167` is the whole
reason: "bejana itu menutup kembali, setitik lebih kosong daripada pagi". One
drop of the reserve is 300 litres of living water, because one drop is the
price the page actually shows for one minor healing (`:125`, a boy's cracked
elbow) and the minor rung of modules/physical_state.py is also the cheapest
priced rung. The reserve is 400 drops a game-day, which is 120000 litres, and
nothing banks across the game-day rollover.

The Well turns toward a threat; it never absorbs one. `:89` has heat stopping
at the first skin layer while the vessel stays shut, and `:167` has the reserve
one drop lower that evening with the burn having cost nothing. So the body
resists and the vessel spends nothing (`WELL_COST_DROPS['heat'] == 0`).

Healing is restorative. `:2311`: "Tubuh itu tidak berubah menjadi tubuh yang
lain. Ia hanya kembali kepada apa yang ia sepatutnya jadi kalau enam bulan itu
tidak pernah berlaku." A body returns to its own baseline or not at all.

Columns this would cost against, if a later unit ever needs a ledger:

    maya_rp.character_injuries   severity, body_part, heal_by_game_day,
                                 became_scar, status
    maya_rp.ooc_suspicion        observer_id, suspicion, last_reason

No migration is written by this unit. Canon carries the rules and this module
carries the arithmetic, so there is no table to add and no column to add it to.

Formulas, written out so a test can check them:

    well_spent_drops(spends)        = sum(spends), 0 for an empty list

    well_reserve(spent)             = max(0, WELL_RESERVE_DROPS - spent)

    well_cost(cause)                = WELL_COST_DROPS[cause]

    well_cost_litres(cause)         = well_cost(cause) * LITRES_PER_DROP

    well_can_heal(cause, reserve, target_is_izzat)
                                    = False for himself, for every cause in
                                      WELL_CANNOT, and for a reserve below the
                                      cost
                                    = reserve >= well_cost(cause) otherwise

    well_pour_drops(litres)         = ceil(litres / LITRES_PER_DROP), 0 for 0
                                      pouring 100800 L (the two pools) costs
                                      336 drops, which is 84% of one day

    well_recover(reserve, days)     = min(WELL_RESERVE_DROPS,
                                          reserve + WELL_RECOVERY_DROPS_PER_DAY * days)
                                      monotonic in days, capped at the reserve,
                                      refused for days < 0, unchanged for days = 0

    well_charge_bodies(drops)       = drops // WELL_COST_DROPS['immersion']
                                      336 drops restores 25 bodies

    aegis_band(d)                   = 'full' if d <= 25
                                      'hue'  if 25 < d <= 60
                                      'none' if d > 60

    aegis_read(d, n, blocked)       -> {'band', 'subjects', 'field', 'why'}
                                      blocked: no reading at all
                                      n > 30: one field, dominant intent, no
                                      names

    aegis_fatigued(reads)           = reads >= 300

    aegis_mark_takes(resolved)      = resolved, identity on the bond event

    mark_report(d, same_system, same_world)
                                    = 'none'      across systems
                                    = 'direction' on another world in the
                                      same system
                                    = 'exact'     d <= 1000 m, same world
                                    = 'band'      1000 < d <= 100000 m
                                    = 'direction' d > 100000 m

Nothing here reads the world, and nothing here compels anyone. No Aegis value
is ever an input to another character's action.
"""
from typing import Iterable, Optional, Sequence, Tuple

# ─── The Well: the reserve ──────────────────────────────────────────
WELL_RESERVE_DROPS = 400
# What the vessel holds at the start of a game-day, counted from inside, in
# drops. 400 drops = 120000 litres.

LITRES_PER_DROP = 300
# `:125` spends exactly one drop on a boy's cracked elbow and `:167` finds the
# reserve one drop lower that evening. One drop is one minor healing, and the
# minor rung of physical_state.SEVERITY is the cheapest priced rung.

WELL_RESERVE_LITRES = WELL_RESERVE_DROPS * LITRES_PER_DROP
# 120000 L. The two pools at `:2199` are 14 x 3 x 1.2 m each, so 100800 L for
# both, which is 336 drops and 84% of one day.

WELL_REACH_PACES = 3
# story.md:41, "a pool three paces across". Healing puts him beside the
# bleeding, and that is the plot engine of the power.

WELL_RECOVERY_DROPS_PER_DAY = WELL_RESERVE_DROPS
# The vessel refills overnight. The reserve is per day, not per scene.

WELL_BANKS_UNSPENT = False
# Unspent drops are lost at the rollover. A full reserve is the ceiling.

WELL_CHARGE_DECAY_OPEN_DAYS = 3
WELL_CHARGE_DECAY_SEALED_DAYS = 30
# Charged water is a charge, not a tap. Open water holds for three game-days,
# sealed water for thirty. This is what stops a pool becoming infrastructure.

WELL_COST_DROPS = {
    "heat": 0,       # `:89`. The body stops it; the vessel spends nothing
    "illness": 3,    # poison, fever, exhaustion, at 900 L per patient
    "minor": 1,      # `:125`, the cracked elbow. 300 L, a 3-day heal
    "moderate": 4,   # 1200 L, a 10-day heal
    "severe": 13,    # 3900 L, a 30-day heal
    "immersion": 13, # `:2309`, 40 minutes for one restored body
    "failing": 40,   # 12000 L, dying but not dead
}

WELL_CANNOT = (
    "permanent",  # physical_state.SEVERITY['permanent'], 999 days
    "scar",       # became_scar = true
    "death",      # no engine status of dead changes
    "ageing",     # he cannot return a fifty-year-old to thirty
    "self",       # the one patient he cannot treat
)
# Five refusals, and they are the ceiling in practice. A missing arm is a
# different baseline, not damage beyond one.

# ─── Aegis Sight: range, count, and the ceiling ─────────────────────
AEGIS_FULL_M = 25
# Hue, pulse and layers. Covers a workshop, a hold, a cantina, a lot queue.

AEGIS_HUE_ONLY_M = 60
# Past 25 m the reading degrades to hue. Past 60 m a body is a shape.

AEGIS_SUBJECTS_PER_LOOK = 30
# `:713` reads twenty-six named intents at once. Thirty is the first round
# number above it. Past thirty, the crowd is one field whose hue is the
# dominant intent, never an average and never a dossier.

AEGIS_READS_PER_DAY = 300
# Thirty per look, ten looks. Past it, intent reads hue-only until the next
# game-day rollover. The eye is free, so the story cost is attention.

AEGIS_ALWAYS_ON = True
# story.md:51 and `:621`. It cannot be closed.

AEGIS_NEVER_COMPELS = True
# The ceiling forbids it twice. Mechanically: no Aegis output is ever an input
# to another character's action.

AEGIS_READS = ("hue", "pulse", "layers")
# What a full read returns. A read is a sentence, not a number: "steady
# orange, one layer".

AEGIS_NOT_READ = (
    "thoughts",     # no memory, no plan, no password, no love
    "names",        # `:2071`, "bukan nama"
    "feelings",     # `:2071`, "bukan perasaan"
    "the_future",   # intent is preparation, and preparation can be wrong
    "a_working_facade",   # reads as one clean layer, and so does an honest
                          # person
    "a_construct",  # no living tissue, so no light: `cahaya` is the carrier
    "a_dead_body",
)
# What the eye cannot answer. Intent tells him what a body is ready for; it
# never tells him what the body will do.

AEGIS_BLOCKED_BY = ("bulkhead", "rock", "vacuum", "construct", "dead_body")
# The reading is light. A hull is the world's unit of privacy.

AEGIS_UNREADABLE = ("facade", "single_layer")
# A working facade reads as one clean layer, which is exactly what an honest
# person reads as. The sight returns a body, never a verdict.

MARK_EXACT_M = 1000
MARK_BAND_M = 100000
MARK_CROSSES_SYSTEM = False
# The mark reports direction and distance inside one system and nothing
# across a system boundary. Distance stays real for every other unit.

MARK_REPORTS = ("direction", "distance")
MARK_NEVER_REPORTS = ("name", "thought", "feeling", "future")
# `:2071`: "Bukan nama, bukan fikiran, bukan perasaan: hanya di mana."

AEGIS_LIMITS = (
    ("full read: hue, pulse, layers", AEGIS_FULL_M),
    ("hue only", AEGIS_HUE_ONLY_M),
    ("beyond this, nothing", AEGIS_HUE_ONLY_M),
    ("subjects resolved per look", AEGIS_SUBJECTS_PER_LOOK),
    ("named reads per game-day", AEGIS_READS_PER_DAY),
    ("mark reports an exact figure up to", MARK_EXACT_M),
    ("mark reports a band up to", MARK_BAND_M),
)
# The limits as one table, so the doc and the test read the same numbers.


def well_spent_drops(spends: Iterable[int]) -> int:
    """Drops spent today. The reserve is a sum over the day, not a counter."""
    total = 0
    for drop in spends:
        if drop < 0:
            raise ValueError("a spend cannot be negative")
        total += drop
    return total


def well_reserve(spent_drops: int) -> int:
    """Drops left in the vessel. Floor 0: the reserve never goes negative."""
    if spent_drops < 0:
        raise ValueError("spent_drops cannot be negative")
    return max(0, WELL_RESERVE_DROPS - spent_drops)


def well_cost(cause: str) -> int:
    """Drops one healing act costs. KeyError-free: unknown causes refuse."""
    if cause not in WELL_COST_DROPS:
        raise ValueError(f"unknown healing cause {cause!r}")
    return WELL_COST_DROPS[cause]


def well_cost_litres(cause: str) -> int:
    """The same cost in litres of living water."""
    return well_cost(cause) * LITRES_PER_DROP


def well_can_heal(
    cause: str,
    reserve_drops: int,
    target_is_izzat: bool = False,
) -> bool:
    """Whether the vessel may do this act at all, and whether it can afford it."""
    if target_is_izzat:
        return False
    if cause in WELL_CANNOT:
        return False
    if cause not in WELL_COST_DROPS:
        raise ValueError(f"unknown healing cause {cause!r}")
    if reserve_drops < 0:
        raise ValueError("reserve_drops cannot be negative")
    return reserve_drops >= well_cost(cause)


def well_pour_drops(litres: int) -> int:
    """Drops needed to pour this many litres. A partial drop is a whole drop."""
    if litres < 0:
        raise ValueError("litres cannot be negative")
    if litres == 0:
        return 0
    return -(-litres // LITRES_PER_DROP)


def well_recover(reserve_drops: int, days: int) -> int:
    """Drops after `days` of game-day rollovers. Monotonic, and capped."""
    if reserve_drops < 0:
        raise ValueError("reserve_drops cannot be negative")
    if days < 0:
        raise ValueError("days cannot be negative")
    gained = WELL_RECOVERY_DROPS_PER_DAY * days
    return min(WELL_RESERVE_DROPS, reserve_drops + gained)


def well_charge_bodies(charge_drops: int) -> int:
    """Whole bodies one charge restores, at the immersion price."""
    if charge_drops < 0:
        raise ValueError("charge_drops cannot be negative")
    return charge_drops // WELL_COST_DROPS["immersion"]


def aegis_band(distance_m: float) -> str:
    """How much of the read survives distance: full, hue, or none."""
    if distance_m < 0:
        raise ValueError("distance_m cannot be negative")
    if distance_m <= AEGIS_FULL_M:
        return "full"
    if distance_m <= AEGIS_HUE_ONLY_M:
        return "hue"
    return "none"


def aegis_subjects(subjects: int) -> Tuple[int, bool]:
    """(resolved individually, is one field). Past thirty, the crowd is a field."""
    if subjects < 0:
        raise ValueError("subjects cannot be negative")
    resolved = min(subjects, AEGIS_SUBJECTS_PER_LOOK)
    return resolved, subjects > AEGIS_SUBJECTS_PER_LOOK


def aegis_read(
    distance_m: float,
    subjects: int,
    blocked_by: Optional[str] = None,
) -> dict:
    """A read as four fields, and never as an answer about a person's intent."""
    if distance_m < 0:
        raise ValueError("distance_m cannot be negative")
    if subjects < 0:
        raise ValueError("subjects cannot be negative")

    if blocked_by in AEGIS_BLOCKED_BY:
        return {
            "band": "none",
            "subjects": 0,
            "field": False,
            "why": f"no light through {blocked_by}",
        }

    band = aegis_band(distance_m)
    if band == "none":
        return {
            "band": "none",
            "subjects": 0,
            "field": False,
            "why": f"beyond {AEGIS_HUE_ONLY_M} m a body is a shape",
        }

    resolved, field = aegis_subjects(subjects)
    if blocked_by in AEGIS_UNREADABLE:
        return {
            "band": band,
            "subjects": resolved,
            "field": field,
            "why": "one clean layer: indistinguishable from an honest person",
        }

    why = "one field, dominant intent" if field else "resolved individually"
    if band == "hue":
        why += ", hue only past 25 m"
    return {"band": band, "subjects": resolved, "field": field, "why": why}


def aegis_fatigued(reads_today: int) -> bool:
    """True when intent reads have cost the day's attention."""
    if reads_today < 0:
        raise ValueError("reads_today cannot be negative")
    return reads_today >= AEGIS_READS_PER_DAY


def aegis_mark_takes(bond_action_resolved: bool) -> bool:
    """A mark takes on the touch that resolves a bond-raising action, and no other."""
    return bool(bond_action_resolved)


def mark_report(
    distance_m: float,
    same_system: bool = True,
    same_world: bool = True,
) -> str:
    """What a mark reports: exact, band, direction, or nothing at all."""
    if distance_m < 0:
        raise ValueError("distance_m cannot be negative")
    if not same_system:
        return "none"
    if not same_world:
        return "direction"
    if distance_m <= MARK_EXACT_M:
        return "exact"
    if distance_m <= MARK_BAND_M:
        return "band"
    return "direction"


def aegis_limit_table() -> Sequence[Tuple[str, int]]:
    """The limits, as the table the doc and the test both read."""
    return AEGIS_LIMITS
