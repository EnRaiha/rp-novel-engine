-- Colony state for Arc II's landmarks 3, 5 and the Bukit Kaca outbreak.
--
-- WHAT IS MISSING, AND WHY IT IS ONLY TWO THINGS.
--
-- Landmark 5 is `The Hungry Months`: "a food tier runs out and the dock learns which mouth it feeds
-- last". I said the engine had no food state and that was wrong: `maya_rp.commodities` holds all five
-- tiers of `wiki/rp-dev/FOOD-LADDER-2026-10-02.md` for session 5, each with `category='food'`,
-- `base_price`, `current_price`, `volatility`, `supply` and `demand`. Nutrient Pack at 90,000,000
-- supply against 88,000,000 demand, down to Craft-Preserved Ration at 4,000 against 38,000.
--
-- So a tier running out is already expressible. What has no home is the sentence's second half:
-- WHICH MOUTH. Nothing records which settlement eats which tier, or in what order they are fed when
-- one runs short. `crew_consumption_log` sits at 0 rows for the same reason: consumption is modelled
-- per crew member and the story's unit is the settlement.
--
-- Two columns, then, and neither invents a number:
--
--   food_commodity  the tier this settlement eats, as a `maya_rp.commodities.name`. A join key, so
--                   the settlement's food is the commodity's supply and demand rather than a second
--                   figure that can disagree with them.
--   food_priority   who eats first. 1 is first. Landmark 5 is `which mouth it feeds last`, and the
--                   last is the maximum here, so the ordering is readable without a second query.
--
-- AND THE BUKIT KACA OUTBREAK FROM TURN 73:
--
--   "Kabus relau menutupi penara pada waktu pagi; dua kes penyakit paru-paru dilaporkan (dalam
--    siasatan Sumayyah)"
--   "Kabus relau. Dua kes paru-paru di Bukit Kaca. Sumayyah meminta penapis atau relau dipindahkan."
--
-- Two active cases, unnamed, under investigation, with a request attached. They belong to the
-- settlement's working conditions, not to a person imagined to carry them, which is why they were left
-- out of the injury seed. `health_status` and `health_notes` give them somewhere to sit.
--
-- NOTHING IS BACKFILLED HERE. The columns arrive empty and the seed script fills what the sources
-- support, because a default tier would be a claim about what people eat and nobody has made it.

ALTER TABLE maya_rp.colonies
    ADD COLUMN IF NOT EXISTS food_commodity TEXT,
    ADD COLUMN IF NOT EXISTS food_priority INTEGER,
    ADD COLUMN IF NOT EXISTS health_status TEXT,
    ADD COLUMN IF NOT EXISTS health_notes TEXT;

COMMENT ON COLUMN maya_rp.colonies.food_commodity IS
    'A maya_rp.commodities.name with category=''food''. The tier this settlement eats. Null means '
    'unrecorded, which is not the same as tier 1.';
COMMENT ON COLUMN maya_rp.colonies.food_priority IS
    'Who eats first when a tier runs short. 1 is first, the largest value is last. Landmark 5 is '
    'which mouth the dock feeds last, and this is the only thing that answers it.';
COMMENT ON COLUMN maya_rp.colonies.health_status IS
    'Unset, watch or outbreak. Null means nobody has said.';
COMMENT ON COLUMN maya_rp.colonies.health_notes IS
    'Working-condition illness and injury at the settlement, where the sufferer is not a named '
    'character. Named injuries live in maya_rp.character_injuries.';
