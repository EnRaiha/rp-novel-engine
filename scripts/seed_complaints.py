#!/usr/bin/env python3
"""seed_complaints.py — Roll 100 complaints from the people (Day 1384, Izzat).

King silent-monitors from the dark. Every Setia planet has a complaint box —
purpose-made tough, can handle beating. People vent there. These are the REAL
voices: taxes, food, governors, species friction, war, hope, fear.

Generates N complaints (`--count`, default 100) across Setia complaint boxes, drawn from
live state: tax rate, dev level, sentiment, species mix, EDEN food coverage.
A session that already has complaints is refused.

  python3 scripts/seed_complaints.py --session N --count 100            # report only
  python3 scripts/seed_complaints.py --session N --count 100 --apply    # insert in one transaction
"""
from __future__ import annotations
import os
import asyncio, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database
from scripts._oneshot import parse, guard

TAX_COMPLAINTS = [
    "Cukai naik lagi tahun ni. Makanan pun mahal. Apa guna box ni kalau cakap pun tak didengar?",
    "Tukang besi kat sini kena cukai tiga kali ganda. Cukai apa ni? Cukai wujud ke?",
    "Saya faham empire besar perlukan duit. Tapi anak saya nak sekolah, bukan nak bayar cukai.",
    "Aku dah pukul box ni sampai penyok. Rasa macam box ni je yang dengar masalah aku.",
    "Cukai perniagaan kecil bunuh kami. Kedai aku tinggal separuh pelanggan.",
]
FOOD_COMPLAINTS = [
    "Dengar kata EDEN kapal makanan datang. Bila? Perut ni dah lama kosong.",
    "Harga beras naik sebab convoy lewat. Box ni boleh bagi makan tak?",
    "Tahun lepas kita cukup makan. Sekarang dok tunggu bekalan. Apa jadi?",
    "Greenhouse komunal rosak sejak dua bulan. Tiada siapa datang baiki.",
]
GOVERNOR_COMPLAINTS = [
    "Gabenor baru kita asyik duduk pejabat je. Tak pernah turun tengok pasar.",
    "Gabenor dengar aduan? Hah. Box ni pun lagi dengar daripada dia.",
    "Deputi gabenor baik orangnya. Tapi bos dia tak nampak muka.",
    "Gabenor naikkan cukai air tanpa beritahu. Kami tahu sebab bil sampai.",
]
WAR_COMPLAINTS = [
    "Anak aku masuk legion. Bangga, tapi takut jugak. Iron Concord tak senyap-senyap.",
    "Berita perang buat harga barang naik. Kami kat sini tak perang pun, tapi bayar juga.",
    "Probe musuh selalu lalu atas kepala kami. Rasa macam duduk dalam sasaran.",
    "Bila perang ni habis? Anak muda semua jadi askar, kampung tinggal orang tua.",
]
SPECIES_COMPLAINTS = [
    "Jiran baru aku species lain. OK je, tapi dia tak faham adat kami. Perlu masa.",
    "Aku hybrid. Kadang rasa tak diterima dua-dua pihak. Box ni pun mungkin tak faham.",
    "Dengar ada diskriminasi kat sektor barat. Harap tak merebak ke sini.",
]
HOPE_COMPLAINTS = [
    "Dengar King ada kapal baru besar. Kalau betul, empire kita memang kuat.",
    "Cakap-cakap kat pasar: King tak mati, dia pergi ambil benda besar. Aku percaya.",
    "Anak aku kata nak jadi askar macam legions. Bangga gila aku.",
    "Cukai tinggi, tapi jalan baru pun siap. Tak tahu nak marah ke nak terima kasih.",
    "Aku dah tua. Dah nampak tiga era. Kali ni rasa macam ada harapan betul.",
]
SPECIAL = [
    "Box ni aku pukul sebab marah. Tapi lepas tu aku rasa lega sikit. Terima kasih sebab ada box ni.",
    "Aku datang semalam pukul box ni. Hari ni datang lagi. Sekurang-kurangnya ada yang dengar.",
    "Sesiapa baca ni — kalau King betul-betul baca aduan, tolong suruh dia tidur cukup. Kami semua risau dia kerja sangat.",
    "Aku tak nak apa-apa. Cuma nak orang tahu aku kat sini, aku hidup, dan aku tak lupa.",
    "Maya. Kalau awak baca ni — suami awak jaga elok-elok. Kami semua doakan dia.",
]

# Faction complaints — even factions use the boxes (deniable channels, beating the box)
FACTION_COMPLAINTS = [
    ("The Vein Collective", "Setia naikkan tarif lagi. Kami bayar, tapi kalau boleh jangan pukul kami dengan cukai dan tarif sekali gus."),
    ("The Vein Collective", "Konvoi kami kena lewatkan tiga hari sebab 'inspeksi rutin'. Rutin apa? Rutin nak susahkan kami je."),
    ("The Mechnoic", "Organic factions tidak faham keperluan kami. Kami perlukan lithium, bukan simpati."),
    ("The Mechnoic", "Probe kami 'hilang' berdekatan sistem Setia. Kami hantar probe, bukan provokasi."),
    ("The Silent Choir", "Kami hanya menyanyi. Semua orang takut dengan bunyi. Bunyi tak bunuh orang."),
    ("The Silent Choir", "Bisik tendril kami kacau. Itu tempat lama kami. Hormat sejarah sikit."),
    ("The Succubi Court", "Maria. Kami tahu dia ada. Kami tak minta dia balik — kami minta status dia jelas."),
    ("The Demon Legions", "Legion kamu tersusun. Legion kami juga. Satu hari kita boleh banding. Box ni pun tak akan redam bunyi tu."),
    ("The Fairy Courts", "Biji benih kami berharga. Rhea tahu. Bila nak buka saluran perdagangan benih yang sebenar?"),
    ("The Dwarf Holdings", "Lombong kami berkualiti. Harga kami adil. Kalau tak beli, jangan halang pembeli lain."),
    ("The Half-Beast Clans", "Anak-anak kami takkan jadi askar kamu. Mereka jadi pemburu. Tak sama."),
    ("The Ghost Chorus", "Kami bising? Galaxy ni yang bising. Kami cuma gema."),
    ("The Swarm", "Banyak. Kami banyak. Jangan panggil kami ancaman, panggil kami realiti."),
    ("The Cyber Collective", "Upgrade sukarela. Semua sukarela. Tapi yang tak mahu upgrade, mereka ketinggalan sendiri."),
    ("The Clone Legions", "Kami semua sama. Tapi diperlakukan tak sama. Itu aduan kami."),
    ("Iron Concord", "Warmaster kata kita perang. Kami kata kita tengok dulu. Kotak ni untuk pendapat yang tak berani cakap depan council."),
    ("The Rim Council", "Kami dulu pusat. Sekarang pinggir. Kotak aduan pun rasa jauh dari kami."),
    ("The Ashen Corsairs", "Kami ada wilayah sendiri sekarang. Kami bayar apa yang patut. Jangan hantar kapal perang 'melawat'."),
    ("The Marrow Fleet", "Lautan kami lapar. Bukan sebab kami jahat — sebab kami ramai."),
    ("The Gutterhawk Marauders", "Kami rompak sebab takde pilihan. Beri kami pilihan, kami berhenti. Box ni pilihan kami."),
]

CATEGORIES = ["tax", "food", "governor", "war", "species", "hope", "special", "faction"]


async def main(argv=None) -> int:
    args = parse(__doc__, argv, extra=lambda parser: parser.add_argument(
        "--count", type=int, default=100, help="complaints to roll"))
    guard(args)
    sid = args.session
    n = args.count
    await Database.init()
    boxes = await Database.fetch(
        """SELECT cb.id, cb.territory_id, t.controlling_faction AS fac
           FROM maya_rp.complaint_boxes cb
           JOIN maya_rp.territory t ON t.id = cb.territory_id
           WHERE cb.session_id=$1""", sid)
    if not boxes:
        print("No complaint boxes seeded")
        await Database.close()
        return 1
    already = await Database.fetchval("SELECT count(*) FROM maya_rp.complaints WHERE session_id=$1", sid)
    if already:
        print(f"REFUSED: session {sid} already has {already} complaints")
        await Database.close()
        return 1

    rng = random.Random(1384)
    rows: list[tuple] = []
    for _ in range(n):
        box = rng.choice(boxes)
        cat = rng.choices(CATEGORIES, weights=[22, 15, 13, 13, 7, 13, 4, 13])[0]
        if cat == "faction":
            fac_name, text = rng.choice(FACTION_COMPLAINTS)
            mood = "rasmi"
            # Faction complaints land in faction-governed boxes mostly
            box = rng.choice([b for b in boxes if b.get("territory_id") and (b.get("fac") or "") != ""] or boxes)
        else:
            fac_name = None
            pool = {"tax": TAX_COMPLAINTS, "food": FOOD_COMPLAINTS, "governor": GOVERNOR_COMPLAINTS,
                    "war": WAR_COMPLAINTS, "species": SPECIES_COMPLAINTS, "hope": HOPE_COMPLAINTS,
                    "special": SPECIAL}[cat]
            text = rng.choice(pool)
            mood = {"tax": "marah", "food": "lapar", "governor": "kecewa", "war": "takut",
                    "species": "harap", "hope": "yakin", "special": "campur"}[cat]
        complaint_text = f"[{fac_name}] {text}" if fac_name else text
        rows.append((sid, box["id"], box["territory_id"], complaint_text, cat, mood))
    print(f"COMPLAINTS ROLLED — {len(rows)} aduan dari {len(boxes)} kotak aduan (rakyat + faction)")
    if not args.apply:
        print("DRY RUN — re-run with --apply to write.")
        await Database.close()
        return 0

    async with Database.transaction() as conn:
        for row in rows:
            await conn.execute(
                """INSERT INTO maya_rp.complaints
                   (session_id, box_id, planet_id, territory_id, complaint, category, mood, anonymous)
                   VALUES ($1,$2,NULL,$3,$4,$5,$6,TRUE)""",
                *row)
    print(f"APPLIED — inserted {len(rows)} complaints")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))