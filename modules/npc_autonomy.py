#!/usr/bin/env python3
"""NPC Autonomy — crew have internal lives, off-screen interactions, personal reactions."""
from __future__ import annotations
import random, json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

ARCHETYPES = {
    "loyalist": {"reaction":"slow","social":"low","ambition":"low","fear":"stand_firm","off_screen":["maintains_equipment","trains","writes_reports"]},
    "socialite": {"reaction":"fast","social":"high","ambition":"medium","fear":"seek_group","off_screen":["gossips","organizes_events","mediates"]},
    "ambitious": {"reaction":"medium","social":"medium","ambition":"high","fear":"calculate","off_screen":["schemes","cultivates_allies","seeks_promotion"]},
    "anxious": {"reaction":"fast","social":"low","ambition":"low","fear":"withdraw","off_screen":["hides","overworks","seeks_reassurance"]},
    "stoic": {"reaction":"slow","social":"very_low","ambition":"low","fear":"suppress","off_screen":["solitary_training","maintains_weapons","watches"]},
    "rebellious": {"reaction":"fast","social":"high","ambition":"high","fear":"defy","off_screen":["complains","recruits_discontent","breaks_rules"]},
    "nurturer": {"reaction":"medium","social":"high","ambition":"low","fear":"protect_others","off_screen":["cooks","checks_on_wounded","grows_plants"]},
}
EVENT_REACTIONS = {"combat_victory":{"m":2,"f":-1,"l":1},"combat_defeat":{"m":-3,"f":3,"l":-2},"crew_death":{"m":-2,"f":2,"l":-1},"prisoner_escape":{"m":-1,"f":1,"l":-1},"resource_crisis":{"m":-2,"f":2,"l":-1},"cabinet_scandal":{"m":-1,"f":0,"l":-2},"diplomatic_success":{"m":2,"f":-1,"l":1},"holiday":{"m":3,"f":-1,"l":0},"brutality_revealed":{"m":-3,"f":4,"l":-3}}

async def react_to_event(event_type: str, session_id: int = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    shifts = EVENT_REACTIONS.get(event_type)
    if not shifts: return []
    npcs = await Database.fetch("SELECT c.id,c.name,c.archetype,nis.personal_morale,nis.personal_fear,nis.personal_loyalty,nis.current_mood FROM maya_rp.characters c LEFT JOIN maya_rp.npc_internal_state nis ON nis.character_id=c.id AND nis.session_id=$1 WHERE c.session_id=$1 AND c.status='active' AND c.role NOT IN ('wife','player')", session_id)
    unknown = {str(n.get("archetype")) for n in npcs} - set(ARCHETYPES)
    if unknown:
        # The live column carries pirate, leader, royal_child, immortal and NULL for
        # most rows, so every one of those NPCs reacted as a stoic without a word.
        info("npc_autonomy", f"archetype(s) {sorted(unknown)} are not in ARCHETYPES; "
                             f"{len(npcs)} NPCs react as stoic")
    notable = []
    for npc in npcs:
        a = ARCHETYPES.get(str(npc.get("archetype")), ARCHETYPES["stoic"])
        mult = 0.5 if a["reaction"]=="slow" else 1.5 if a["reaction"]=="fast" else 1.0
        md = int(shifts["m"]*mult); fd = int(shifts["f"]*mult); ld = int(shifts["l"]*mult)
        if "cabinet" in event_type and a["ambition"]=="high": ld *= 2
        if "death" in event_type and a["fear"]=="protect_others": md *= 2; fd *= 2
        # `or 50` read a stored 0 as a missing value, the same way a bond of 0 was
        # read in characters.resolve_intent. Only None takes the default.
        m0 = npc.get("personal_morale"); f0 = npc.get("personal_fear"); l0 = npc.get("personal_loyalty")
        nm = max(0,min(100,(50 if m0 is None else m0)+md))
        nf = max(0,min(100,(0 if f0 is None else f0)+fd))
        nl = max(0,min(100,(50 if l0 is None else l0)+ld))
        mood = "terrified" if nf>70 else "broken" if nm<20 else "demoralized" if nm<35 else "anxious" if nf>50 else "discontent" if nl<30 else "euphoric" if nm>80 and nf<20 else "content" if nm>65 else "stable" if nm>50 else "wary"
        await Database.execute("INSERT INTO maya_rp.npc_internal_state(character_id,session_id,personal_morale,personal_fear,personal_loyalty,current_mood,last_reaction_event) VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(character_id,session_id)DO UPDATE SET personal_morale=$3,personal_fear=$4,personal_loyalty=$5,current_mood=$6,last_reaction_event=$7", npc["id"],session_id,nm,nf,nl,mood,event_type)
        if abs(md)>=3 or abs(ld)>=3 or nf>70 or nm<20:
            notable.append({"name":npc["name"],"archetype":npc.get("archetype"),"mood":mood,"morale_delta":md,"fear_delta":fd,"loyalty_delta":ld})
    notable.sort(key=lambda n:abs(n["morale_delta"])+abs(n["loyalty_delta"])+n.get("fear_delta",0)/10,reverse=True)
    return notable[:5]

async def _generate_off_screen(session_id: int) -> list[dict]:
    if random.random()>0.3: return []
    npcs = await Database.fetch("SELECT id,name,archetype FROM maya_rp.characters WHERE session_id=$1 AND status='active' AND role NOT IN ('wife','player')", session_id)
    if len(npcs)<2: return []
    pair = random.sample([dict(n) for n in npcs],2)
    aa = ARCHETYPES.get(str(pair[0].get("archetype")),ARCHETYPES["stoic"])
    ba = ARCHETYPES.get(str(pair[1].get("archetype")),ARCHETYPES["stoic"])
    if aa["social"]=="very_low" and ba["social"]=="low": return []
    interactions = []
    if aa["social"]=="high" and ba["social"]=="high":
        t = random.choice([("gossip",f"{pair[0]['name']} and {pair[1]['name']} were deep in conversation."),("alliance",f"{pair[0]['name']} and {pair[1]['name']} seem to have formed a bond.")])
    elif aa["ambition"]=="high" and ba["ambition"]!="low":
        t = ("recruitment",f"{pair[0]['name']} pulled {pair[1]['name']} aside for a private word.")
    elif aa["fear"]=="protect_others" and ba["fear"] in ("withdraw","seek_group"):
        t = ("comfort",f"{pair[0]['name']} sat with {pair[1]['name']} for a long time.")
    elif aa["fear"]=="defy" and ba["fear"]=="defy":
        t = ("conspiracy",f"{pair[0]['name']} and {pair[1]['name']} were seen heads together in cargo.")
    else:
        t = ("shared_meal",f"{pair[0]['name']} and {pair[1]['name']} ate together.")
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    await Database.execute("INSERT INTO maya_rp.npc_offscreen_interactions(session_id,character_a,character_b,interaction_type,description,game_day) VALUES($1,$2,$3,$4,$5,$6)", session_id,pair[0]["id"],pair[1]["id"],t[0],t[1],gd)
    interactions.append({"type":t[0],"description":t[1],"characters":[pair[0]["name"],pair[1]["name"]]})
    return interactions

async def discover_off_screen(session_id: int = None) -> dict | None:
    if session_id is None: session_id = Config.SESSION_ID
    r = await Database.fetchrow("SELECT * FROM maya_rp.npc_offscreen_interactions WHERE session_id=$1 AND discovered=false ORDER BY game_day ASC LIMIT 1", session_id)
    if not r: return None
    await Database.execute("UPDATE maya_rp.npc_offscreen_interactions SET discovered=true WHERE id=$1", r["id"])
    an = await Database.fetchval(
        "SELECT name FROM maya_rp.characters WHERE id=$1 AND session_id=$2",
        r["character_a"], session_id)
    bn = await Database.fetchval(
        "SELECT name FROM maya_rp.characters WHERE id=$1 AND session_id=$2",
        r["character_b"], session_id)
    return {"type":r["interaction_type"],"description":r["description"],"discovery":random.choice([f"You overhear {an} and {bn} talking in low voices.",f"You notice {an} and {bn} exchanging a look.",f"A crewman mentions {an} and {bn} have been spending time together."]),"characters":[an,bn]}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    interactions = await _generate_off_screen(session_id)
    await Database.execute("UPDATE maya_rp.npc_internal_state SET personal_fear=GREATEST(0,personal_fear-1),personal_morale=LEAST(100,personal_morale+1) WHERE session_id=$1", session_id)
    anx = await Database.fetch("SELECT c.name FROM maya_rp.npc_internal_state nis JOIN maya_rp.characters c ON c.id=nis.character_id WHERE nis.session_id=$1 AND nis.personal_fear>60", session_id)
    if anx and random.random()<0.2:
        rs = random.choice(anx)["name"]
        await Database.execute("INSERT INTO maya_rp.events(session_id,happened_at,event_type,title,description,tags) VALUES($1,NOW(),'rumor','Whispered Rumors',$2,$3)", session_id, f"Rumors spreading through lower decks. {rs} seems to be at the center.", '["rumor","npc"]')
    return {"off_screen":len(interactions),"anxious":len(anx)}
