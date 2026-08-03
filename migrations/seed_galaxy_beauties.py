#!/usr/bin/env python3
"""
Seed all 40 Galaxy Beauties with JSONB profiles + add 10 new ones.

Reads the catalog and generates fitting face/body/voice/wardrobe/inventory
based on each beauty's theme (Immortal, Scientist, Warrior, Pilot, etc.).

Run: python3 migrations/seed_galaxy_beauties.py
"""
import asyncio, sys, json, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.db import Database
from core.config import Config

# ─── Theme-based Appearance Generators ─────────────────────────────────
# Each generates {face, body, voice} from the character's theme + name

def _immortal_appearance(name: str, flavor: str) -> dict:
    """Immortals are otherworldly, luminous, transcendent."""
    eyes_opts = ["Luminous silver with flecks of gold", "Deep violet with no visible pupils",
                 "Shifting opal—never the same colour twice", "Solid white, iris and pupil merged into one",
                 "Flecked with what looks like distant galaxies"]
    hair_opts = ["Floating, translucent, defies gravity", "Long and silver-white, moves like water",
                 "Fiberoptic threads that shift colour with mood", "Crystalline, catches light like prism",
                 "Drifts around the head as if underwater"]
    skin_opts = ["Pale with a faint pearlescent shimmer", "Smooth as polished stone, cool to the touch",
                 "Warm amber glow, like sunlight through honey", "Faintly luminous in darkness"]
    build_opts = ["Ethereal and slender, seems to weigh less than she should",
                  "Statuesque with otherworldly grace, glides rather than walks",
                  "Wiry and ageless, impossible to guess her age"]
    voice_opts = ["Soft, resonant hum—like a cello played from far away",
                  "Layered, as if two people speak in perfect unison",
                  "Melodic, with harmonics that shouldn't come from a human throat",
                  "Quiet thunder, words arrive a moment after her lips move"]

    return {
        "face": {
            "eyes": eyes_opts[hash(name + "eyes") % len(eyes_opts)],
            "hair": hair_opts[hash(name + "hair") % len(hair_opts)],
            "skin": skin_opts[hash(name + "skin") % len(skin_opts)],
            "features": f"Flawless symmetry. {flavor[:80]}"
        },
        "body": {
            "build": build_opts[hash(name + "build") % len(build_opts)],
            "height": ["5'7\"","5'9\"","5'11\"","6'0\""][hash(name + "h") % 4],
            "distinguishing": "Moves with a grace that seems rehearsed—but it's not."
        },
        "voice": voice_opts[hash(name + "v") % len(voice_opts)],
    }

def _mortal_scientist_appearance(name: str, flavor: str) -> dict:
    """Scientists: focused, sharp, slightly dishevelled."""
    return {
        "face": {
            "eyes": ["Sharp, observant", "Tired but brilliant", "Intense, magnified by thick spectacles",
                     "Quick, darting—always reading something"][hash(name+"e")%4],
            "hair": ["Haphazard bun held together by a pen", "Cropped short, practical", "Messy ponytail, often singed at the ends",
                     "Pulled back severely, not a strand out of place"][hash(name+"h")%4],
            "skin": ["Lab-pale", "Warm tan with a perpetual smudge of grease", "Freckled, rarely sees sunlight"],
            "features": f"Calloused fingertips from years of fine manipulation. {flavor[:80]}"
        },
        "body": {
            "build": "Slender, slightly hunched from leaning over workbenches",
            "height": ["5'4\"","5'6\"","5'8\"","5'3\""][hash(name+"h2")%4],
            "distinguishing": "Fidgets with tools when thinking. Always has a datapad within reach."
        },
        "voice": ["Rapid, enthusiastic when explaining her work", "Quiet and precise, chooses words carefully",
                  "Warm but distracted, trailing off mid-sentence"][hash(name+"v")%3],
    }

def _mortal_warrior_appearance(name: str, flavor: str) -> dict:
    """Warriors: scarred, alert, powerful."""
    return {
        "face": {
            "eyes": ["Steel-hard, have seen too much", "Pale and unflinching", "Keen, miss nothing in peripheral",
                     "Warm but sharp—kindness with an edge"][hash(name+"e")%4],
            "hair": ["Cropped close for practical reasons", "Tied in a severe ponytail", "Short, with a streak of white from an old injury",
                     "Worn loose but always pushed out of the way"][hash(name+"h")%4],
            "skin": ["Weathered, a faint scar traces her jaw", "Tan with a network of fine scars on the forearms",
                     "Pale, with a tattoo peeking above the collar"],
            "features": f"Posture is perfect. Always. {flavor[:80]}"
        },
        "body": {
            "build": "Compact, muscular. Built for violence, not show.",
            "height": ["5'6\"","5'8\"","5'5\"","5'10\""][hash(name+"h2")%4],
            "distinguishing": "Scans every room upon entering. Old habit. Still alive because of it."
        },
        "voice": ["Low and steady, never flustered", "Raspy, from years of shouting over gunfire",
                  "Quiet, which makes everyone lean in"][hash(name+"v")%3],
    }

def _mortal_pilot_appearance(name: str, flavor: str) -> dict:
    """Pilots: lean, restless, always looking at the sky."""
    return {
        "face": {
            "eyes": ["Keen, squint lines from staring into deep space", "Bright, alive, always looking at the horizon",
                     "Reflective—you can see the stars in them"][hash(name+"e")%3],
            "hair": ["Wild, windswept", "Dyed an impossible colour (neon blue, deep crimson)", "Short and practical, never in the way of a helmet",
                     "Long, braided back tight"][hash(name+"h")%4],
            "skin": ["Sun-kissed from cockpit windows", "Pale from deep space, freckles like star charts",
             "Warm, with a permanent squint-line tan"][hash(name+"sk")%3],
            "features": f"Grins too much. She can't help it—she loves the sky. {flavor[:60]}"
        },
        "body": {
            "build": "Lean, wiry. High-G training keeps her dense.",
            "height": ["5'4\"","5'6\"","5'7\"","5'9\""][hash(name+"h2")%4],
            "distinguishing": "Taps her fingers in flying patterns when bored."
        },
        "voice": ["Bright, infectious. The kind of voice that makes you smile.", "Raspy from yelling 'pull up!' too many times.",
                  "Calm, steady—the voice you want in a storm."][hash(name+"v")%3],
    }

def _mortal_diplomat_appearance(name: str, flavor: str) -> dict:
    """Diplomats: poised, elegant, controlled."""
    return {
        "face": {
            "eyes": ["Assessing, warm but calculating", "Sharp jade, appraises everything in seconds",
                     "Deep brown, unreadable—a professional poker face"][hash(name+"e")%3],
            "hair": ["Immaculate chignon, not a strand out of place", "Sleek bob, precision-cut",
                     "Long, worn loose but perfectly controlled"][hash(name+"h")%3],
            "skin": ["Flawless, expensive skincare", "Warm, with a professional smile that reaches the eyes",
                     "Pale, never caught in the sun without SPF"],
            "features": f"Knows exactly how she looks at every angle. Uses it. {flavor[:80]}"
        },
        "body": {
            "build": "Elegant, carries herself like she owns the room.",
            "height": ["5'7\"","5'8\"","5'10\"","5'9\""][hash(name+"h2")%4],
            "distinguishing": "Always wears heels. Even when it makes no sense."
        },
        "voice": ["Controlled mezzo-soprano. Never raises it—doesn't need to.",
                  "Silky, with an edge of steel. Polite until it's not.",
                  "Warm RP accent. Every word is measured."][hash(name+"v")%3],
    }

def _mortal_engineer_appearance(name: str, flavor: str) -> dict:
    """Engineers: grease-stained, intense, brilliant."""
    return {
        "face": {
            "eyes": ["Intense, focused. Sparks of genius visible.", "Bright, magnified by safety goggles",
                     "Tired— hasn't slept in days. Still brilliant."][hash(name+"e")%3],
            "hair": ["Tucked under a bandana or cap", "Wild and frazzled from running hands through it",
                     "Practical ponytail, often with a welding spatter"][hash(name+"h")%3],
            "skin": ["Olive with permanent grease stains on the hands", "Fair, smudged with graphite",
                     "Warm, has a burn scar on one forearm from a plasma cutter"],
            "features": f"Fingernails are never clean. She doesn't care. {flavor[:80]}"
        },
        "body": {
            "build": "Sturdy, capable. Used to carrying heavy tools.",
            "height": ["5'3\"","5'5\"","5'7\"","5'8\""][hash(name+"h2")%4],
            "distinguishing": "Still wearing steel-toed boots. Even at dinner."
        },
        "voice": ["Direct, no-nonsense", "Warm when talking about her work, clipped when interrupted",
                  "Raspy from yelling over machinery"][hash(name+"v")%3],
    }

def _mortal_artist_appearance(name: str, flavor: str) -> dict:
    """Artists: expressive, striking, unconventional."""
    return {
        "face": {
            "eyes": ["Expressive, change colour with the light", "Deep and knowing, see beauty everywhere",
                     "Bold, lined with dark pigment—stage eyes"][hash(name+"e")%3],
            "hair": ["Dyed an impossible gradient—purple to blue to pink", "Dreadlocks woven with glowing fibres",
                     "Shaved on one side, long on the other", "Natural, wild, untouched by stylists"][hash(name+"h")%4],
            "skin": ["Pale, adorned with temporary light-tattoos", "Warm, one sleeve of permanent ink",
                     "Flawless, used as a canvas for holographic projections"],
            "features": f"Always looks like she just stepped off a stage. {flavor[:80]}"
        },
        "body": {
            "build": "Expressive, moves like music even when standing still.",
            "height": ["5'5\"","5'7\"","5'8\"","5'10\""][hash(name+"h2")%4],
            "distinguishing": "Gestures when she talks. Big, sweeping motions."
        },
        "voice": ["Rich, melodic—trained", "Raw, textured. A voice that's lived.",
                  "Soft with sudden bursts of passion"][hash(name+"v")%3],
    }

def _mortal_explorer_appearance(name: str, flavor: str) -> dict:
    """Explorers: rugged, curious, weather-beaten."""
    return {
        "face": {
            "eyes": ["Bright, curious. The eyes of someone who has seen impossible things.",
                     "Deep-set, squint-lined from staring into alien suns",
                     "Warm, crinkle at the corners when she smiles"][hash(name+"e")%3],
            "hair": ["Sun-bleached, tied back carelessly", "Wild curls, windswept", 
                     "Cropped short, practical for helmet seals"][hash(name+"h")%3],
            "skin": ["Weather-beaten, golden tan from a dozen different suns",
                     "Fair with a permanent sunburn across the nose",
                     "Rugged, a scar on her cheek from a fall on an uncharted world"],
            "features": f"Has a map of every place she's ever been. In her head. {flavor[:80]}"
        },
        "body": {
            "build": "Rugged, lean. At home in any gravity.",
            "height": ["5'5\"","5'7\"","5'8\"","5'9\""][hash(name+"h2")%4],
            "distinguishing": "Always carries a physical notebook. Digital fails. Paper doesn't."
        },
        "voice": ["Warm, storytelling voice. Could listen to her for hours.",
                  "Raspy from talking over wind and engine noise.",
                  "Calm, measured. Nothing phases her."][hash(name+"v")%3],
    }

# ─── Theme → generator mapping ────────────────────────────────────────
CATEGORY_GENERATORS = {
    "immortals": _immortal_appearance,
    "scientists": _mortal_scientist_appearance,
    "warriors": _mortal_warrior_appearance,
    "pilots": _mortal_pilot_appearance,
    "diplomats": _mortal_diplomat_appearance,
    "engineers": _mortal_engineer_appearance,
    "artists": _mortal_artist_appearance,
    "explorers": _mortal_explorer_appearance,
}

# ─── Map each DB character name to catalog info ────────────────────────
# (name_in_db, theme_category, skill_keyword, has_weapon)
BEAUTY_MAP = [
    # IMMORTALS
    ("Seraphina Vey", "immortals", "star", False),
    ("Mira", "immortals", "vein_network", False),
    ("Aeliana", "immortals", "oracle", False),
    ("Nyx", "immortals", "shadow", True),
    ("Celestine Voss", "immortals", "forge", False),
    ("Eira Snow", "immortals", "frost", False),
    ("Selene Nyxaris", "immortals", "dream", False),
    ("Vespera Tide", "immortals", "song", False),
    ("Aurora Solis", "immortals", "aurora", False),
    ("Chronis Vale", "immortals", "time", False),
    ("Nova Reign", "immortals", "rebirth", False),
    ("Luna Starweaver", "immortals", "moon", False),
    # SCIENTISTS
    ("Dr Rania Zahir", "scientists", "xenobiology", False),
    ("Professor Lyra Chen", "scientists", "signal", False),
    ("Isha Nakamura", "scientists", "linguist", False),
    ("Dr Zara El-Amin", "scientists", "physics", False),
    # WARRIORS
    ("Valeria Stone", "warriors", "fleet", False),
    ("Kira Blackwood", "warriors", "shadow_ops", True),
    ("Sera Vanguard", "warriors", "bodyguard", True),
    ("Jade Hawkins", "warriors", "bounty", True),
    # PILOTS
    ("Stella Cosmos", "pilots", "ace", False),
    ("Nadia Voss", "pilots", "navigator", False),
    ("Raina Stormrider", "pilots", "racer", False),
    ("Mira Solara", "pilots", "vein", False),
    # DIPLOMATS
    ("Lady Serena Ashford", "diplomats", "ambassador", False),
    ("Cassandra Vale", "diplomats", "negotiator", False),
    ("Isabella Hart", "diplomats", "trade", False),
    ("Tiana Moreau", "diplomats", "culture", False),
    # ENGINEERS
    ("Maya Khatri", "engineers", "shipwright", False),
    ("Helena Frost", "engineers", "quantum", False),
    ("Petra Stonewall", "engineers", "architect", False),
    ("Lena Volkov", "engineers", "weapons", False),
    # ARTISTS
    ("Aria Moonlight", "artists", "holovision", False),
    ("Sakura Blossom", "artists", "dancer", False),
    ("Raven Noir", "artists", "musician", False),
    ("Crystal Dawn", "artists", "light", False),
    # EXPLORERS
    ("Athena Drake", "explorers", "explorer", True),
    ("River Phoenix", "explorers", "archaeologist", False),
    ("Sierra Wild", "explorers", "surveyor", False),
    ("Nova Drake", "explorers", "anomaly", False),
]

# ─── Items by theme ───────────────────────────────────────────────────
WEAPON_ITEMS = [
    {"name": "Plasma Blade", "slot": "held", "desc": "Magnetic hilt, energy blade deploys on activation. Signature weapon."},
    {"name": "Tactical Pistol", "slot": "holstered", "desc": "Compact sidearm, custom grip. Always within reach."},
    {"name": "Combat Knife", "slot": "worn", "desc": "Ceramic blade, strapped to the thigh. Last resort."},
]

SKILL_ITEMS = {
    "star": [{"name": "Stellar Compass", "slot": "worn", "desc": "Navigates by starlight. Pointed at a specific nebula."}],
    "vein_network": [{"name": "Vein Echo Fragment", "slot": "visible", "desc": "A shard of crystallised Vein energy. Pulses faintly."}],
    "oracle": [{"name": "Probability Deck", "slot": "held", "desc": "Tattered cards. Each shows a possible future."}],
    "shadow": [{"name": "Shadow Shroud", "slot": "worn", "desc": "A cloak that seems to drink light around it."}],
    "forge": [{"name": "Stellar Hammer", "slot": "held", "desc": "Tool that has forged metals in stellar cores. Still warm."}],
    "frost": [{"name": "Cryo-Key", "slot": "worn", "desc": "Her cryopod activation key. Keeps it as a memento."}],
    "dream": [{"name": "Dream-Catcher", "slot": "visible", "desc": "Woven from lunar silk. Captures nightmares."}],
    "song": [{"name": "Harmonic Resonator", "slot": "held", "desc": "Focuses her voice into precise frequencies."}],
    "aurora": [{"name": "EM Field Regulator", "slot": "worn", "desc": "Wrist-mounted. Helps her control electromagnetic output."}],
    "time": [{"name": "Temporal Lens", "slot": "worn", "desc": "Glasses that let her see time as a physical dimension."}],
    "rebirth": [{"name": "Memory Stone", "slot": "worn", "desc": "A smooth stone from her garden. Warm to the touch."}],
    "moon": [{"name": "Tide Pearl", "slot": "visible", "desc": "A pearl from her favourite moon's ocean. Still damp."}],
    "xenobiology": [{"name": "Alien Flora Sample", "slot": "held", "desc": "A glowing plant in a sealed container. Purrs when content."}],
    "signal": [{"name": "Ghost Signal Decoder Ring", "slot": "worn", "desc": "A ring that vibrates when the Signal is active."}],
    "linguist": [{"name": "Precursor Lexicon", "slot": "held", "desc": "Ancient book. Annotated heavily in three colours of ink."}],
    "physics": [{"name": "Exotic Matter Vial", "slot": "visible", "desc": "Gleaming silver liquid in a magnetic containment field."}],
    "fleet": [{"name": "Vintage Fleet Badge", "slot": "worn", "desc": "Her original command insignia. Polished daily."}],
    "shadow_ops": [{"name": "Identity Chip Set", "slot": "holstered", "desc": "A case of 12 different IDs. All genuine."}],
    "bodyguard": [{"name": "Protection Detail Log", "slot": "holstered", "desc": "Every protection assignment, annotated in her code."}],
    "bounty": [{"name": "Wanted Poster Collection", "slot": "held", "desc": "Her favourite catches. Signed by each one."}],
    "ace": [{"name": "Racing Trophy", "slot": "visible", "desc": "Miniature. Gold. First place, TKG Grand Prix."}],
    "navigator": [{"name": "Gravitic Sensor Pendant", "slot": "worn", "desc": "Necklace that hums near gravity wells."}],
    "racer": [{"name": "Engine Component", "slot": "held", "desc": "High-performance thruster nozzle. Signed by the designer."}],
    "vein": [{"name": "Vein-Thread Map", "slot": "holstered", "desc": "Eternal, shifting map of the Vein Network. Hand-drawn."}],
    "ambassador": [{"name": "Treaty Seal Ring", "slot": "worn", "desc": "Ring with the seal of 14 treaties she negotiated."}],
    "negotiator": [{"name": "Failed Draft Collection", "slot": "holstered", "desc": "5 drafts of treaties that didn't pass. Lessons in ink."}],
    "trade": [{"name": "Physical Ledger", "slot": "held", "desc": "Leather-bound notebook. Her empire recorded in cursive."}],
    "culture": [{"name": "Multi-Flag Scarf", "slot": "worn", "desc": "Scarf woven with 14 cultural patterns. Each means 'welcome'."}],
    "shipwright": [{"name": "Model Ship", "slot": "held", "desc": "Miniature of a ship she designed. Tears at launch day."}],
    "quantum": [{"name": "Binary-Printed Poem", "slot": "worn", "desc": "A poem written in binary. Only she can read it."}],
    "architect": [{"name": "Scale Model Ring", "slot": "worn", "desc": "Ring that is actually a perfect scaled habitat ring."}],
    "weapons": [{"name": "Personal Railgun Prototype", "slot": "holstered", "desc": "Her sidearm. Custom. Devastating."}],
    "holovision": [{"name": "Director's Viewfinder", "slot": "worn", "desc": "Framed her eye. Shows scenes before they're shot."}],
    "dancer": [{"name": "Weightless Ribbons", "slot": "visible", "desc": "Floating ribbons that orbit her. Zero-g performance tools."}],
    "musician": [{"name": "Bone-Instrument Picks", "slot": "holstered", "desc": "Guitar picks carved from... something organic."}],
    "light": [{"name": "Prism Focus", "slot": "worn", "desc": "Crystal that bends light into shapes. Her sketching tool."}],
    "explorer": [{"name": "First-World Rock Sample", "slot": "held", "desc": "A piece of the first uncharted world she stepped on."}],
    "archaeologist": [{"name": "Precursor Shard", "slot": "visible", "desc": "Fragment of a precursor data disc. Still humming."}],
    "surveyor": [{"name": "Soil Sample Jar", "slot": "holstered", "desc": "A tiny jar of purple sand from a double-sunset world."}],
    "anomaly": [{"name": "Anomaly Tracker", "slot": "held", "desc": "Device that beeps when near spacetime irregularities."}],
}

# ─── Theme-based wardrobe generator ────────────────────────────────────
def _generate_wardrobe(name: str, theme: str, skill: str) -> list[dict]:
    """Generate 3 outfits based on character theme."""
    casual_tag = ["casual", "downtime"]
    if theme == "immortals":
        return [
            {"id": "default_form", "name": f"Default Form", "desc": f"Her natural appearance. Luminous and otherworldly.", "tags": ["casual", "intimate", "formal"]},
            {"id": "combat_form", "name": f"Hard-Light Sheath", "desc": f"Geometric plates of solidified energy. Glows faintly.", "tags": ["combat", "tactical"]},
            {"id": "casual", "name": f"Borrowed Shape", "desc": f"A carefully chosen outfit from mortal fashion. Helps her blend in.", "tags": ["casual", "exploration", "downtime"]},
        ]
    elif theme == "warriors":
        return [
            {"id": "combat", "name": f"Tactical Harness", "desc": f"Armoured webbing over a compression top. Scarred from use.", "tags": ["combat", "tactical", "military"]},
            {"id": "casual", "name": f"Off-Duty", "desc": f"Comfortable jacket, worn jeans. Scar tissue visible on forearms.", "tags": ["casual", "downtime", "intimate"]},
            {"id": "formal", "name": f"Dress Uniform", "desc": f"Crisp jacket, medals. She looks uncomfortable but stunning.", "tags": ["formal", "political"]},
        ]
    elif theme == "pilots":
        return [
            {"id": "flight_suit", "name": f"Flight Suit", "desc": f"Form-fitting pressure suit. Patches from every squadron.", "tags": ["tactical", "exploration"]},
            {"id": "casual", "name": f"Leather & Starlight", "desc": f"Worn leather jacket, simple shirt, confident grin.", "tags": ["casual", "downtime", "intimate"]},
            {"id": "formal", "name": f"Gala Attire", "desc": f"Elegant dress. She cleans up well—but can't wait to get back to the cockpit.", "tags": ["formal", "social"]},
        ]
    elif theme in ("diplomats",):
        return [
            {"id": "business", "name": f"Power Suit", "desc": f"Tailored, expensive. Projects authority before she speaks.", "tags": ["formal", "political"]},
            {"id": "casual", "name": f"Relaxed Elegance", "desc": f"Cashmere, silk, understated jewellery. Relaxed but expensive.", "tags": ["casual", "downtime", "social"]},
            {"id": "travel", "name": f"Travel Ensemble", "desc": f"Long coat, practical but stylish. Ready for any port.", "tags": ["exploration", "formal"]},
        ]
    elif theme in ("scientists", "engineers"):
        return [
            {"id": "lab", "name": f"Lab Wear", "desc": f"Stained lab coat over practical clothes. Pockets full of tools.", "tags": ["tactical", "exploration"]},
            {"id": "casual", "name": f"After Hours", "desc": f"Comfortable sweater. She looks different without safety goggles.", "tags": ["casual", "downtime", "intimate"]},
            {"id": "formal", "name": f"Conference Ready", "desc": f"Blazer and slacks. She cleans up well, but keeps a pen in her pocket.", "tags": ["formal", "social"]},
        ]
    elif theme in ("artists",):
        return [
            {"id": "stage", "name": f"Performance Wear", "desc": f"Dramatic, expressive. Designed to be seen from the back row.", "tags": ["formal", "social", "intimate"]},
            {"id": "casual", "name": f"Studio Mode", "desc": f"Comfortable, paint-stained. The real work happens here.", "tags": ["casual", "downtime"]},
            {"id": "street", "name": f"Street Style", "desc": f"Bold fashion. She dresses like she's curating a gallery.", "tags": ["casual", "social", "exploration"]},
        ]
    else:  # explorers
        return [
            {"id": "field", "name": f"Field Gear", "desc": f"Durable, multi-pocket. Has seen every environment.", "tags": ["exploration", "tactical"]},
            {"id": "casual", "name": f"Camp Comfort", "desc": f"Soft flannel, worn boots. At home anywhere.", "tags": ["casual", "downtime", "intimate"]},
            {"id": "formal", "name": f"Expedition Formal", "desc": f"The nicest clothes she owns. Still has a compass in the pocket.", "tags": ["formal", "social"]},
        ]


async def main():
    await Database.init()
    sid = Config.SESSION_ID
    total = 0

    for (name, theme, skill, has_weapon) in BEAUTY_MAP:
        char = await Database.fetchrow(
            "SELECT id FROM maya_rp.characters WHERE session_id=$1 AND LOWER(name)=LOWER($2)",
            sid, name,
        )
        if not char:
            print(f"  ⚠️  '{name}' — not found in DB, skipping")
            continue

        cid = char["id"]
        generator = CATEGORY_GENERATORS.get(theme, _mortal_explorer_appearance)
        flavor_text = f"Known for: {skill.replace('_',' ')}."
        profile = generator(name, flavor_text)

        wardrobe = _generate_wardrobe(name, theme, skill)
        current_outfit = wardrobe[1] if len(wardrobe) > 1 else wardrobe[0]

        # Inventory: skill item + optional weapon
        inventory = []
        skill_item = SKILL_ITEMS.get(skill)
        if skill_item:
            inventory.extend(skill_item)
        if has_weapon:
            inventory.append(WEAPON_ITEMS[len(inventory) % len(WEAPON_ITEMS)])

        await Database.execute(
            """UPDATE maya_rp.characters
               SET profile_jsonb=$1, wardrobe_jsonb=$2, current_outfit=$3, inventory_jsonb=$4
               WHERE id=$5""",
            json.dumps(profile), json.dumps(wardrobe),
            json.dumps(current_outfit), json.dumps(inventory), cid,
        )
        print(f"  ✅ {name:30s} {theme:12s} {len(wardrobe)} outfits, {len(inventory)} items")
        total += 1

    await Database.close()
    print(f"\nSeeded {total}/{len(BEAUTY_MAP)} Galaxy Beauties with profiles.")

if __name__ == "__main__":
    asyncio.run(main())
