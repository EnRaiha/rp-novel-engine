#!/usr/bin/env python3
"""
Seed character profiles — populates profile_jsonb, wardrobe_jsonb, current_outfit, inventory_jsonb
for all priority characters in the TKG universe.

Run: python3 migrations/seed_character_profiles.py
"""
import asyncio, sys, json, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.db import Database
from core.config import Config

PROFILES = {
    # ─── MAYA ─────────────────────────────────────────────────────
    "Maya": {
        "profile": {
            "face": {
                "eyes": "Warm, intelligent amber. Holds eye contact with unwavering focus.",
                "hair": "Long, dark auburn, usually worn in a practical braid or loose over one shoulder.",
                "skin": "Warm olive. A faint constellation of freckles across the nose.",
                "features": "Expressive eyebrows, quick to smile. A small scar on her left temple from her first deployment."
            },
            "body": {
                "build": "Athletic, toned. Not bulky—built for endurance and agility.",
                "height": "5'7\"",
                "distinguishing": "Stands with perfect posture, hands clasped behind her back when thinking."
            },
            "voice": "Warm contralto. Slight Malaysian accent. Drops an octave when giving orders."
        },
        "wardrobe": [
            {"id": "adjutant_uniform", "name": "Adjutant Dress Uniform", "desc": "Navy-blue jacket with gold piping, white shirt underneath, fitted black trousers. TKG fleet insignia on the collar.", "tags": ["formal", "political", "military"]},
            {"id": "combat_gear", "name": "Field Harness", "desc": "Tactical webbing over a grey compression top. Armoured plates on shoulders and forearms. Sidearm holster.", "tags": ["combat", "tactical"]},
            {"id": "casual", "name": "Off-Duty Civvies", "desc": "Soft cream sweater, dark jeans, boots. She looks almost ordinary, except for the way she watches the room.", "tags": ["casual", "downtime", "intimate"]},
            {"id": "sleepwear", "name": "Night Layers", "desc": "Thin cotton tank top and loose sleep shorts. No armour. No rank. Just Maya.", "tags": ["intimate", "sleepwear"]},
        ],
        "outfit": "casual",
        "inventory": [
            {"name": "Command Datapad", "slot": "held", "desc": "Thin, armoured tablet with fleet network access."},
            {"name": "Service Pistol", "slot": "holstered", "desc": "Standard TKG-issue sidearm, worn at the hip."},
        ],
    },

    # ─── RIKA VOSS ─────────────────────────────────────────────────
    "Rika Voss": {
        "profile": {
            "face": {
                "eyes": "Sharp steel-grey. The kind that have seen too much and flinch at nothing.",
                "hair": "Short, silver-white, cropped close at the sides. Longer on top, usually pushed back.",
                "skin": "Fair, weathered. Fine lines around the eyes from years on the bridge.",
                "features": "Strong jaw, straight nose. A thin scar runs from her right earlobe down her neck—never explains it."
            },
            "body": {
                "build": "Lean, wiry. Deceptive strength—she's stronger than she looks.",
                "height": "5'9\"",
                "distinguishing": "Keeps her hands on her hips or crossed. Rarely sits still."
            },
            "voice": "Raspy tenor. Permanently hoarse from years of yelling over engine noise. Cuts through a room."
        },
        "wardrobe": [
            {"id": "captain_uniform", "name": "Captain's Dress Uniform", "desc": "Deep burgundy coat with brass buttons, pressed black trousers. Four rings on the cuff.", "tags": ["formal", "political", "military"]},
            {"id": "bridge_gear", "name": "Bridge Duty Wear", "desc": "Fitted black jacket with ship insignia, comfortable trousers, low-profile boots.", "tags": ["military", "tactical"]},
            {"id": "civilian", "name": "Port Leave Attire", "desc": "Leather jacket over a simple shirt, worn jeans, scuffed boots. Looks like she could still outfly you.", "tags": ["casual", "downtime"]},
        ],
        "outfit": "bridge_gear",
        "inventory": [
            {"name": "Vintage Compass", "slot": "worn", "desc": "Old brass compass, non-functional, kept in her breast pocket as a good-luck charm."},
            {"name": "Command Key", "slot": "worn", "desc": "Physical key to the Nusantara's auxiliary console. Worn on a chain around her neck."},
        ],
    },

    # ─── SARA VALDEZ ──────────────────────────────────────────────
    "Leftenan Sara Valdez": {
        "profile": {
            "face": {
                "eyes": "Bright hazel. Alert, curious. Misses nothing.",
                "hair": "Dark brown, pulled into a tight, efficient bun. A few strands always escape.",
                "skin": "Warm tan.",
                "features": "Youthful face that makes her look younger than her rank. Has learned to harden her expression on command."
            },
            "body": {
                "build": "Compact, energetic. Moves like she's always about to be called somewhere.",
                "height": "5'5\"",
                "distinguishing": "Fidgets with her sleeve cuff when thinking. Stands at attention automatically around senior officers."
            },
            "voice": "Bright, clear soprano. Slight nervous edge that disappears when she's focused."
        },
        "wardrobe": [
            {"id": "acting_uniform", "name": "Acting Adjutant Uniform", "desc": "Standard TKG duty uniform with acting-adjutant armband. Crisp, clean, pride in every stitch.", "tags": ["formal", "military"]},
            {"id": "field_gear", "name": "Survey Field Kit", "desc": "Light jacket with many pockets, reinforced trousers, sturdy boots. Ready for ground duty.", "tags": ["tactical", "exploration", "casual"]},
        ],
        "outfit": "acting_uniform",
        "inventory": [
            {"name": "Maya's Manual", "slot": "holstered", "desc": "A physical binder of protocols Maya left behind. Annotated heavily in red ink."},
            {"name": "Datapad", "slot": "held", "desc": "Standard issue, screen cracked at the corner."},
        ],
    },

    # ─── CASSANDRA VALE ────────────────────────────────────────────
    "Cassandra Vale": {
        "profile": {
            "face": {
                "eyes": "Sharp, calculating jade. She appraises everything—people, deals, ships—in seconds.",
                "hair": "Platinum blonde, swept into an immaculate chignon. Not a strand out of place.",
                "skin": "Pale, flawless. Expensive skincare regimen.",
                "features": "High cheekbones, thin lips that curve into a knowing smile. Horn-rimmed spectacles she doesn't need—they're a prop."
            },
            "body": {
                "build": "Slender, elegant. Carries herself like she owns the room.",
                "height": "5'10\"",
                "distinguishing": "Always wears heels, even on the station. Taps her rings against surfaces when calculating."
            },
            "voice": "Controlled mezzo-soprano. RP English. Never raises it—doesn't need to."
        },
        "wardrobe": [
            {"id": "banking_attire", "name": "Governor's Suit", "desc": "Impeccably tailored navy pantsuit with a silk blouse. The TKG treasury pin gleams on her lapel.", "tags": ["formal", "political"]},
            {"id": "casual_luxury", "name": "High-End Casual", "desc": "Cashmere sweater, tailored trousers, minimalist jewellery. Relaxed but expensive.", "tags": ["casual", "downtime", "social"]},
            {"id": "travel", "name": "Travel Ensemble", "desc": "Long coat, silk scarf, leather gloves. Practical for ship travel, elegant enough for a boardroom.", "tags": ["exploration", "formal"]},
        ],
        "outfit": "banking_attire",
        "inventory": [
            {"name": "Treasury Seal", "slot": "held", "desc": "Gold-embossed credential case containing the Royal Bank master key."},
            {"name": "Data Slate", "slot": "holstered", "desc": "Ultra-thin, encrypted. Contains the Kingdom's bond ledgers."},
        ],
    },

    # ─── SERAPHINA VEY ────────────────────────────────────────────
    "Seraphina Vey": {
        "profile": {
            "face": {
                "eyes": "Luminous silver with flecks of gold—like staring into a nebula. No visible pupils in dim light.",
                "hair": "Floating, translucent white. Drifts around her head as if underwater. Never seems to obey gravity.",
                "skin": "Pale with a faint shimmer. Cool to the touch.",
                "features": "Angelic, otherworldly. Too symmetrical. Her expression is one of gentle, perpetual wonder."
            },
            "body": {
                "build": "Ethereal, slender. Seems to weigh less than she should.",
                "height": "5'8\"",
                "distinguishing": "Barefoot, always. The soles of her feet never touch the ground—she hovers a centimetre above."
            },
            "voice": "Soft, resonant hum. Like a cello played from very far away. Words arrive a fraction of a second after her lips move."
        },
        "wardrobe": [
            {"id": "stellar_form", "name": "Nebula Veil", "desc": "A dress of shifting light and cosmic dust that obscures more than it reveals. Changes colour with ambient starlight.", "tags": ["formal", "intimate", "exploration"]},
            {"id": "human_form", "name": "Borrowed Shape", "desc": "A simple white sundress she found somewhere. Still barefoot. Still floating.", "tags": ["casual", "downtime"]},
        ],
        "outfit": "stellar_form",
        "inventory": [
            {"name": "A Star's Heart", "slot": "visible", "desc": "A small, pulsing orb of light that orbits her hand when she's thinking."},
        ],
    },
}


async def main():
    await Database.init()
    sid = Config.SESSION_ID
    total = 0

    for name, data in PROFILES.items():
        char = await Database.fetchrow(
            "SELECT id FROM maya_rp.characters WHERE session_id=$1 AND LOWER(name)=LOWER($2)",
            sid, name,
        )
        if not char:
            print(f"  Skipping '{name}' — not found in DB")
            continue

        cid = char["id"]
        profile_json = json.dumps(data["profile"])
        wardrobe_json = json.dumps(data["wardrobe"])

        # Find the default outfit
        default_outfit_id = data.get("outfit")
        current_outfit = data["wardrobe"][0]  # fallback
        if default_outfit_id:
            match = next((o for o in data["wardrobe"] if o["id"] == default_outfit_id), None)
            if match:
                current_outfit = match
        current_outfit_json = json.dumps(current_outfit)
        inventory_json = json.dumps(data.get("inventory", []))

        await Database.execute(
            """UPDATE maya_rp.characters
               SET profile_jsonb = $1, wardrobe_jsonb = $2,
                   current_outfit = $3, inventory_jsonb = $4
               WHERE id = $5""",
            profile_json, wardrobe_json, current_outfit_json, inventory_json, cid,
        )
        print(f"  ✅ {name} — {len(data['wardrobe'])} outfits, {len(data.get('inventory',[]))} items")
        total += 1

    await Database.close()
    print(f"\nSeeded {total} character profiles.")


if __name__ == "__main__":
    asyncio.run(main())
