"""name_gen.py — unique name generator for TKG RP.

⚠️ FOR RP NARRATIVE ONLY — NOT OFFICIAL RECORDS (Izzat, Day 1481).
Nama generik untuk scene/crew/characters dalam roleplay. Dokumen rasmi,
census, dan ledger rasmi guna nama yang ditetapkan canon — bukan generator ini.

Replaces hardcoded cyclical name lists (crew_system.py) that guaranteed
duplicates and collided with canon characters (Mira, Chen, Lina, Wira...).

Rules (Izzat, Day 1481):
1. Names must be UNIQUE — check against characters + crew_roster + slaves.
2. Malaysian flavor — Malay/Chinese/Indian/East/Western pools, not Western default.
3. No canon collisions — never generate a name that matches an existing
   character (SAME NAME, DIFFERENT PERSON rule).
4. **PATRONYMIC CANCELLED** — tiada bin/binti. Family name guna dua sistem:
   - old_way (clan): "Ahmad Abdullah"
   - setia_new_way (RULE — Izzat): isteri kahwin al-Dabaran tapi KEKAL
     nama keluarga sendiri ("Rika Voss"). ANAK — DUA PERINGKAT:
       * LAHIR: ibu atau bapa pilih (decided_by='mother'/'father')
       * DEWASA: anak pilih sendiri — boleh kekal atau tukar.
       Hassel, tapi itu cara mereka buat keputusan sendiri.
5. father_name → guna terus sebagai family name ("Nabil Izzat").
6. Deterministic retry: bounded attempts, then suffix with roman numeral.

Usage:
    from core.name_gen import unique_name
    name = await unique_name(conn, prefix="", culture="mixed")
"""
import asyncio
import random

# --- Malay first names (NO family name — patronymic bin/binti) ---
MELAYU_FIRST_M = [
    "Aidil", "Aiman", "Amir", "Aqil", "Arif", "Azlan", "Badrul", "Farid", "Hafiz",
    "Haziq", "Iman", "Irfan", "Kamil", "Khairul", "Malik", "Nabil", "Naufal",
    "Omar", "Rafiq", "Rizal", "Shah", "Umar", "Wira", "Yusuf", "Zul",
]
MELAYU_FIRST_F = [
    "Aisyah", "Anisa", "Ayu", "Balqis", "Dania", "Danisha", "Dewi", "Farah",
    "Fatin", "Hana", "Iffah", "Izzah", "Laila", "Layla", "Nafisa", "Nur",
    "Qistina", "Sara", "Siti", "Wani", "Yana", "Zahra",
]
# Father names for patronymic (bin/binti <FatherName>)
PATRONYM_FATHERS = [
    "Abdullah", "Ahmad", "Ali", "Anwar", "Bakar", "Daud", "Elias", "Faizal",
    "Hakim", "Hamid", "Hassan", "Ibrahim", "Ismail", "Jamil", "Mahmud", "Manaf",
    "Mat", "Othman", "Osman", "Rahman", "Raja", "Razak", "Samad", "Sulaiman",
    "Yusof", "Zainal", "Zulkifli",
]

# --- Chinese family names (surname FIRST in Malaysia) ---
CHINESE_FAMILY = [
    "Chen", "Cheah", "Chin", "Chong", "Goh", "Hoe", "Koh", "Lee", "Lim", "Loh",
    "Ng", "Ong", "Tan", "Tay", "Teo", "Wong", "Yap",
]
CHINESE_GIVEN = [
    "Wei", "Ming", "Jia", "Kai", "Hui", "Mei", "Ling", "Jun", "Yan", "Xin",
    "Bo", "Han", "Yi", "Fang", "Lei", "Ting", "Yu", "Zi", "Qiang", "Shan",
]

# --- Indian family names ---
INDIAN_FAMILY = [
    "Kaur", "Singh", "Perumal", "Santhanam", "Kumar", "Rajan", "Muniandy",
    "Devi", "Lakshmi", "Pillai", "Mohan", "Sundaram", "A/p Krishnan",
]
INDIAN_GIVEN_M = ["Gopal", "Ravi", "Kumar", "Arul", "Ramesh", "Vijay", "Suresh", "Kannan"]
INDIAN_GIVEN_F = ["Kavita", "Priya", "Rani", "Vani", "Devi", "Lakshmi", "Meena", "Shanti"]

# --- East (Japanese-flavored) ---
EAST_FAMILY = ["Tanaka", "Suzuki", "Yamamoto", "Watanabe", "Nakamura", "Kobayashi", "Sato"]
EAST_GIVEN = ["Aiko", "Kenji", "Rin", "Sakura", "Yuki", "Haru", "Mei", "Jin", "Sora", "Hana"]

# --- Western ---
WESTERN_FIRST = ["Elena", "Ewan", "Bella", "Lina", "Maya", "Sara", "Dewi", "Farid", "Laila", "Ivan", "Jia", "Cara"]
WESTERN_LAST = ["Baker", "Chen", "Costa", "Drake", "Ellis", "Ford", "Grant", "Hill", "Ivey", "James"]

# Culture distribution for "mixed" (Malaysian demographics: ~70% Malay, 20% Chinese, 10% Indian)
MIXED_CULTURES = ["malay"] * 7 + ["chinese"] * 2 + ["indian"] * 1

#: Cultures `_compose` and `unique_name` accept. Anything else raises: the old
#: fallback returned a Malay name, so "chinse" produced plausible output and no error.
VALID_CULTURES = ("mixed", "malay", "chinese", "indian", "east", "western")


class NameGenerator:
    """Async name generator with DB uniqueness guarantee."""

    def __init__(self, conn=None):
        self.conn = conn
        self._seen = set()  # session-local guard (works without DB too)

    def set_conn(self, conn):
        self.conn = conn

    @staticmethod
    def _malay_given(rng):
        """The one place that knows how a Malay given name is drawn.

        Shared by `_compose` and `_compose_malay_first` so the two copies of the
        Malay rule cannot drift apart again.
        """
        is_male = rng.random() < 0.5
        return rng.choice(MELAYU_FIRST_M if is_male else MELAYU_FIRST_F)

    @staticmethod
    def _compose(culture="mixed", seed=None, family_rate=0.85):
        """Compose a culturally-correct Malaysian name.

        - malay:  NO patronymic (cancelled, Day 1481): "Ahmad Abdullah" or "Ahmad"
        - mixed:  one draw from MIXED_CULTURES (~70% Malay, 20% Chinese, 10% Indian)
        - chinese: surname FIRST: "Lim Wei Ming" (family name — correct for Cina)
        - indian:  "Ravi Kumar" / "Kavita Kaur" (family name)
        - east:    "Kenji Tanaka" (family name)
        - western: "Elena Baker" (family name)

        An unknown culture raises ValueError rather than returning a Malay name.
        """
        rng = random.Random(seed)
        if culture == "mixed":
            culture = rng.choice(MIXED_CULTURES)
        if culture not in VALID_CULTURES:
            raise ValueError(f"unknown culture {culture!r}; expected one of {VALID_CULTURES}")

        if culture == "malay":
            # MELAYU: tiada patronimik bin/binti (Izzat, Day 1481). The rule lives
            # in _compose_malay_first; this branch only decides whether the family
            # name is carried at all.
            if rng.random() < family_rate:
                return NameGenerator._compose_malay_first(seed=rng.randint(0, 2**31))
            return NameGenerator._malay_given(rng)  # single name (common for Melayu)
        elif culture == "chinese":
            # Cina Malaysia: surname FIRST — "Lim Wei Ming"
            family = rng.choice(CHINESE_FAMILY)
            given = rng.choice(CHINESE_GIVEN)
            return f"{family} {given}"
        elif culture == "indian":
            given = rng.choice(INDIAN_GIVEN_M if rng.random() < 0.5 else INDIAN_GIVEN_F)
            family = rng.choice(INDIAN_FAMILY)
            return f"{given} {family}"
        elif culture == "east":
            return f"{rng.choice(EAST_GIVEN)} {rng.choice(EAST_FAMILY)}"
        elif culture == "western":
            return f"{rng.choice(WESTERN_FIRST)} {rng.choice(WESTERN_LAST)}"
        raise ValueError(f"unknown culture {culture!r}; expected one of {VALID_CULTURES}")

    @staticmethod
    def _compose_malay_first(seed=None, with_bin=False):
        """Malay name + family name, Malaysian style.

        NO patronymic (bin/binti) — Izzat cancelled it (Day 1481).
        "Ahmad Abdullah" — given name + family name, plain.

        `with_bin=True` asks for the cancelled rule, so it raises instead of
        returning a plain name the caller did not ask for.
        """
        if with_bin:
            raise ValueError("patronymic bin/binti cancelled (Day 1481); compose given + family name")
        rng = random.Random(seed)
        first = NameGenerator._malay_given(rng)
        family = rng.choice(PATRONYM_FATHERS)
        return f"{first} {family}"

    async def _exists(self, name: str, prefix: str = "") -> bool:
        """Check name against characters + crew_roster + slaves, and this generator's own output.

        Exact, case-insensitive match on the full name and on the bare name (prefix stripped). The
        old `name ILIKE '%<name>%'` was a substring match over unescaped text: "Amir" was rejected
        because "Samir Khan" exists (exhausting the attempts), "TKG Ahmad Abdullah" missed canon
        "Ahmad Abdullah" (SAME NAME, DIFFERENT PERSON), and `%`/`_` in a family name were wildcards.

        @param name: candidate, with any role prefix, e.g. "TKG Ahmad Abdullah".
        @param prefix: the role tag carried by `name`, e.g. "TKG"; its bare form is checked too.
        @returns: True when the name is taken.
        """
        if name in self._seen:
            return True
        if self.conn is None:
            return False
        candidates = [name]
        if prefix and name.startswith(prefix + " "):
            candidates.append(name[len(prefix) + 1:])
        row = await self.conn.fetchrow(
            """SELECT 1 FROM (
                 SELECT name FROM maya_rp.characters
                 UNION ALL
                 SELECT name FROM maya_rp.crew_roster
                 UNION ALL
                 SELECT name FROM maya_rp.slaves
               ) t WHERE lower(name) = ANY($1::text[]) LIMIT 1""",
            [c.lower() for c in candidates])
        return row is not None

    async def unique_name(self, culture="mixed", prefix="", max_attempts=30, family_rate=0.85,
                          father_name=None, family_system="old_way", family_names=None,
                          decided_by=None) -> str:
        """Generate a unique name, bounded retries, roman-numeral fallback.

        prefix: optional role tag, e.g. "TKG" -> "TKG Ahmad Abdullah".
        family_system (Izzat, Day 1481 — patronymic CANCELLED):
          - "old_way"      : family name = clan/house — "Ahmad Abdullah"
          - "setia_new_way": SETIA NAMING RULE (Izzat):
              * isteri kahwin al-Dabaran tapi KEKAL nama keluarga sendiri:
                "Rika Voss" — Voss kekal, al-Dabaran = gelaran sahaja
              * ANAK — DUA PERINGKAT KEPUTUSAN:
                  - LAHIR: ibu atau bapa pilih (decided_by)
                      decided_by='mother' -> nama keluarga ibu ("Nabil Voss")
                      decided_by='father' -> nama rumah bapa ("Nabil al-Dabaran")
                  - DEWASA (coming of age): anak pilih sendiri — boleh
                    kekal atau tukar. Hassel, tapi itu cara mereka buat
                    keputusan sendiri. (Update chars.family_choice bila
                    anak besar — generator tak boleh forecast.)
        family_names (list): pilihan family name — ['Voss','al-Dabaran'].
        father_name: bila diberi, guna SEBAGAI family name terus
                     (no bin/binti): "Nabil Izzat" bukan "Nabil bin Izzat"
        culture: "mixed" (default, one draw from MIXED_CULTURES), or one of
                 "malay", "chinese", "indian", "east", "western". An unknown
                 culture raises ValueError. When family_names or father_name is
                 given the family is the supplied one, so the given name comes
                 from the Malay pool and culture is not consulted.
        family_rate: probability a Malay name carries a family name at all.
        Culture collisions are ALSO checked (Mira vs Mira (Ghost...) etc.).
        """
        if family_names and father_name:
            raise ValueError("pass family_names or father_name, not both: they are two family-name rules")
        if not culture:
            culture = "mixed"
        if culture not in VALID_CULTURES:
            raise ValueError(f"unknown culture {culture!r}; expected one of {VALID_CULTURES}")

        def _base(numeral: str = "") -> str:
            """One candidate. Suffix is carried by the caller's numeral, if any."""
            tail = f" {numeral}" if numeral else ""
            if family_names:
                if decided_by == "mother":
                    # Ibu pilih: nama keluarga ibu (Voss)
                    given = self._malay_given(rng)
                    return f"{given} {family_names[0]}{tail}"
                if decided_by == "father":
                    # Bapa pilih: nama rumah bapa (al-Dabaran — last in list)
                    given = self._malay_given(rng)
                    return f"{given} {family_names[-1]}{tail}"
                # Tiada penentu — rawak (fallback)
                return f"{self._malay_given(rng)} {rng.choice(family_names)}{tail}"
            if father_name:
                # family name = father's name, no patronymic marker
                return f"{self._malay_given(rng)} {father_name}{tail}"
            composed = self._compose(culture=culture, seed=rng.randint(0, 2**31),
                                     family_rate=family_rate)
            return f"{composed}{tail}"

        def _full(base: str) -> str:
            return f"{prefix} {base}".strip() if prefix else base

        rng = random.Random()
        for attempt in range(max_attempts):
            full = _full(_base())
            if not await self._exists(full, prefix):
                self._seen.add(full)
                return full
        # Exhausted: append a roman numeral. Every numeral is CHECKED — the old
        # fallback returned its first pick unverified and called that a guarantee.
        roman = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
        rng.shuffle(roman)
        for numeral in roman:
            full = _full(_base(numeral))
            if not await self._exists(full, prefix):
                self._seen.add(full)
                return full
        raise RuntimeError(
            f"name_gen exhausted {max_attempts} attempts and {len(roman)} roman suffixes"
            f" (prefix={prefix!r}, culture={culture!r})")

    async def unique_crew_name(self, prefix=""):
        """Crew-specific: C1-C4 generic, no title prefix by default."""
        return await self.unique_name(culture="mixed", prefix=prefix)


# Module-level singleton for convenience
_generator = NameGenerator()


def set_global_conn(conn):
    _generator.set_conn(conn)


async def unique_name(conn=None, culture="mixed", prefix="", max_attempts=30, family_rate=0.85,
                      father_name=None, family_system="old_way", family_names=None,
                      decided_by=None) -> str:
    """Convenience wrapper: create ephemeral generator with given conn."""
    gen = NameGenerator(conn)
    return await gen.unique_name(culture=culture, prefix=prefix, max_attempts=max_attempts,
                                 family_rate=family_rate, father_name=father_name,
                                 family_system=family_system, family_names=family_names,
                                 decided_by=decided_by)


if __name__ == "__main__":
    # Self-test without DB (session-local uniqueness only)
    async def _test():
        g = NameGenerator(None)
        names = [await g.unique_name() for _ in range(8)]
        for n in names:
            print(n)
        print(f"unique: {len(set(names)) == len(names)}")

    asyncio.run(_test())
