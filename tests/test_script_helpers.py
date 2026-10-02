"""The pure helpers inside today's scripts.

Four scripts write to the world or to the canon, and each one has helper functions where the
real decisions live: how a scene is split, which clause counts as an appearance, what beauty
a row gets, and which keys a name may match on. Those helpers are tested here without touching
the database, because each of them was wrong at least once before a dry run caught it.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


novel_faces = _load("novel_faces")
beauty_list = _load("beauty_list")
cast_appearance = _load("cast_appearance")
face_manifest = _load("face_manifest")


class TestNovelFaces:
    def test_scenes_split_on_level_two_headings(self):
        text = "---\ntitle: x\n---\n## Satu\n\nbody\n\n## Dua\n\nbody dua\n"
        found = novel_faces.scenes(text)
        assert [heading for heading, _ in found] == ["Satu", "Dua"]
        assert "body" in "\n".join(found[0][1])

    def test_a_scene_claims_a_character_through_the_id_tag(self):
        body = ["**Ersya Ardani (id 2947)** masuk dan duduk."]
        ready = {2947: {"neutral": "path/neutral.png"}}
        chosen, missing = novel_faces.scene_faces(body, ready, cap=4)
        assert chosen == [(2947, "path/neutral.png")]
        assert missing == []

    def test_a_character_with_no_file_is_reported_not_dropped(self):
        body = ["**Suri Okonjo (id 2985)** menulis."]
        chosen, missing = novel_faces.scene_faces(body, {}, cap=4)
        assert chosen == []
        assert missing == [2985]

    def test_the_cap_holds_and_the_rest_are_still_counted(self):
        body = ["(id %d)" % cid for cid in (1, 2, 3, 4, 5)]
        ready = {cid: {"neutral": f"{cid}.png"} for cid in (1, 2, 3, 4, 5)}
        chosen, missing = novel_faces.scene_faces(body, ready, cap=2)
        assert len(chosen) == 2
        assert missing == []

    def test_first_mention_decides_the_order(self):
        body = ["(id 9) dulu", "(id 4) kemudian", "(id 9) sekali lagi"]
        ready = {cid: {"neutral": f"{cid}.png"} for cid in (4, 9)}
        chosen, _ = novel_faces.scene_faces(body, ready, cap=4)
        assert [cid for cid, _ in chosen] == [9, 4]


class TestBeautyBasis:
    ROW = {"catalog": None, "role": "5-star · Fusion · Sword — Jinzhou", "id": 1, "name": "x"}

    def test_rank_basis_rewards_a_top_rank(self):
        assert beauty_list.beauty_for(self.ROW, "rank", 9.0) == 9.5
        assert beauty_list.beauty_for({**self.ROW, "role": "4-star · Glacio"}, "rank", 9.0) == 9.0

    def test_uniform_basis_ignores_the_role(self):
        assert beauty_list.beauty_for(self.ROW, "uniform", 9.0) == 9.0

    def test_a_gap_in_the_data_is_visible_as_the_floor(self):
        """PGR and Genshin rows carry no rank, so the basis cannot tell them apart."""
        row = {**self.ROW, "role": "Construct, Gray Raven — attacker frame"}
        assert beauty_list.beauty_for(row, "rank", 9.0) == 9.0

    def test_s_rank_counts(self):
        row = {**self.ROW, "role": "S-rank · Electric · Support — Victoria Housekeeping"}
        assert beauty_list.beauty_for(row, "rank", 9.0) == 9.5

    def test_the_floor_is_configurable(self):
        assert beauty_list.beauty_for({**self.ROW, "role": "none"}, "rank", 8.5) == 8.5


class TestAppearanceParser:
    LINE = ("**Halima Wreda (id 2949)**. Perempuan. Campuran Bumi-limbah, dua puluh sembilan "
            "tahun. Rambut diikat rapi di belakang. Niatnya: pulang dengan laporan.")

    def test_the_intent_clause_is_dropped(self):
        found = cast_appearance.ledger_lines(self.LINE)
        assert 2949 in found
        _, identity = found[2949]
        assert "Niatnya" not in identity
        assert "Campuran Bumi-limbah" in identity

    def test_a_body_clause_is_claimed(self):
        clause = cast_appearance.physical_clause("Perempuan. Rambut diikat rapi di belakang.")
        assert clause == "Rambut diikat rapi di belakang."

    def test_narration_is_refused(self):
        """The clause must carry a body marker, or this test proves nothing.

        The first version of it used a sentence with no body word in it, so it passed even
        with the narration guard removed. A test that cannot fail is not a test.
        """
        narration = "Dia mengangkat tangannya dan berjalan ke arah saluran mesin pengemas."
        assert cast_appearance.physical_clause(narration) is None
        assert cast_appearance.physical_clause(narration.replace("Dia ", "Lelaki itu ")) is not None

    def test_a_body_clause_beats_an_age_clause(self):
        identity = ("Dua puluh tujuh tahun. Rambut hitam diikat rendah, kot kerja kelabu "
                    "yang kemas.")
        clause = cast_appearance.physical_clause(identity)
        assert clause is not None and "Rambut hitam" in clause

    def test_an_age_alone_is_still_usable(self):
        assert cast_appearance.physical_clause("Dua puluh empat tahun.") == "Dua puluh empat tahun."


class TestManifestKeys:
    def test_a_stored_name_is_always_a_key(self):
        assert "Queen Onyx Sable" in face_manifest.match_keys("Queen Onyx Sable")

    def test_the_epithet_stem_is_a_key(self):
        keys = face_manifest.match_keys("Maya al-Dabaran (Anchor)")
        assert "Maya al-Dabaran" in keys

    def test_a_short_epithet_is_a_key(self):
        assert "Den" in face_manifest.match_keys("Rook Crow (Den)")

    def test_a_partial_first_name_is_never_a_key(self):
        """Claiming 'Zara' from 'Zara-beth' would collide every shared given name."""
        assert face_manifest.match_keys("Zara-beth Cordano") == ["Zara-beth Cordano"]

    def test_whitespace_is_normalised(self):
        assert face_manifest.match_keys("  Doyo   Kwarta  ")[0] == "Doyo Kwarta"


class TestWifeTierResolution:
    """A wife is recognised by her trait first, and by the name join only as a fallback.

    Session 5 records no `is_spouse`, so the manifest used to resolve the wife tier through an
    exact-name join into frozen session 3. The King confirmed the 35 on 2026-10-02 and they carry
    `confirmed-wife`, so the trait is the durable source and the join is the safety net.
    """

    def test_the_trait_wins(self):
        row = {"name": "not in the join", "traits": '["confirmed-wife"]', "background": "", "id": 1}
        assert face_manifest.tier_of(row, set()) == "wife"

    def test_the_name_join_still_works_as_a_fallback(self):
        row = {"name": "Aurelia Veyra", "traits": "[]", "background": "", "id": 2}
        assert face_manifest.tier_of(row, {"Aurelia Veyra"}) == "wife"

    def test_a_stranger_is_not_a_wife(self):
        row = {"name": "Nobody", "traits": '["imported"]', "background": "", "id": 3}
        assert face_manifest.tier_of(row, set()) == "import"


class TestBeautyListKeepsExistingIds:
    """The catalog id binds the readable catalog to the engine, so it is never reassigned.

    The first apply overwrote all 248 candidates: the doc said Queen Onyx Sable was katalog 52 and
    the database said 334. The rule that prevents it is checked here, because the damage is silent
    until someone compares the two.
    """

    def test_the_apply_path_only_assigns_when_the_id_is_missing(self):
        import inspect

        source = inspect.getsource(beauty_list.main)
        assert 'if row["catalog"] is not None:' in source, 'existing ids must be kept'
        assert "beauty_catalog_id = %s WHERE id = %s" in source

    def test_the_free_id_starts_above_every_id_in_use(self):
        import inspect

        source = inspect.getsource(beauty_list.main)
        assert "CATALOG_CEILING" in source, "the start point must ignore the synthetic ceiling"
