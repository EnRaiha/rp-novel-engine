"""Module review: core/embed.py.

NO DEFECT FOUND, and the row names what was checked.

This module is a registry of two model names and two dimensions, and its whole
job is to agree with the vectors that exist. It does. Measured against the live
database: every populated RP-native vector column is 768-dimensional
(`maya_rp.events` 157 rows, `maya_rp.novel_chunks` 104, `maya_rp.stream_templates`
47, `maya_rp.wiki_articles` 265), which is `RP_EMBED_DIM` with
`RP_EMBED_MODEL = nomic-embed-text`. `maya_rag.novel_chunks` is the cortex store
and carries `CORTEX_EMBED_DIM = 1024` with `bge-m3`; it holds no embedded row
today, so the test skips that half rather than asserting on nothing.

The dimension check is the one that matters here: a model name that disagrees with
a store is silent, because a query embeds in one space and compares against
another, and the 2026-09-13 model-mismatch repair was exactly this. The live test
below fails the day a store is re-embedded at another dimension.

REPORTED, not changed, because the file is a script:

- `scripts/novel_rag.py:29` keeps its own default, `EMBED_MODEL =
  os.environ.get("MAYA_EMBED_MODEL", "bge-m3")`, instead of importing
  `CORTEX_EMBED_MODEL` from here. `os.environ.get` with a name no environment
  sets means the model is decided in two places, and this file's own rule is that
  the registry is the single source. `scripts/` belongs to the lead.
- `DEPRECATED_MODELS` is read by nothing. It is policy (`bge-large`,
  `mxbai-embed-large`: no new writes, re-embed on touch) and no code path consults
  it, so nothing refuses a new write with a deprecated model. Pinned here as a set
  that must stay disjoint from the active pair.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import embed  # noqa: E402


class TestTheRegistry:
    """Two active models, two dimensions, one deprecated set."""

    def test_the_active_models_and_their_dimensions(self):
        assert embed.RP_EMBED_MODEL == "nomic-embed-text"
        assert embed.RP_EMBED_DIM == 768
        assert embed.CORTEX_EMBED_MODEL == "bge-m3"
        assert embed.CORTEX_EMBED_DIM == 1024

    def test_the_two_active_models_are_different(self):
        assert embed.RP_EMBED_MODEL != embed.CORTEX_EMBED_MODEL
        assert embed.RP_EMBED_DIM != embed.CORTEX_EMBED_DIM

    def test_no_deprecated_model_is_an_active_model(self):
        assert embed.DEPRECATED_MODELS.isdisjoint({embed.RP_EMBED_MODEL, embed.CORTEX_EMBED_MODEL})

    def test_core_memory_takes_its_model_from_the_registry(self):
        from core import memory

        assert memory.EMBED_MODEL == embed.RP_EMBED_MODEL, \
            "the RP embed path must not decide the model a second time"


class TestTheLiveStores:
    """The registry against the dimensions actually stored."""

    async def _dims(self, schema: str, table: str, column: str = "embedding"):
        import asyncpg

        from core.config import Config

        conn = await asyncpg.connect(Config.DSN)
        try:
            row = await conn.fetchrow(
                f"SELECT vector_dims({column}) AS dim, count(*) AS n FROM {schema}.{table} "
                f"WHERE {column} IS NOT NULL GROUP BY 1"
            )
            return row
        finally:
            await conn.close()

    async def test_every_rp_store_holds_the_rp_dimension(self):
        stores = [
            ("maya_rp", "events", "embedding"),
            ("maya_rp", "novel_chunks", "embedding"),
            ("maya_rp", "stream_templates", "trigger_tag_embed"),
            ("maya_rp", "wiki_articles", "embedding"),
        ]
        checked = 0
        for schema, table, column in stores:
            try:
                row = await self._dims(schema, table, column)
            except Exception as exc:  # noqa: BLE001 - a database that is down is not this module's defect
                pytest.skip(f"live store unreadable: {type(exc).__name__}: {exc}")
            if row is None:
                continue
            assert row["dim"] == embed.RP_EMBED_DIM, \
                f"{schema}.{table}.{column} holds {row['dim']}-dim vectors, registry says {embed.RP_EMBED_DIM}"
            checked += 1

        assert checked, "no populated RP store was checked; the assertion above tested nothing"

    async def test_the_cortex_store_holds_the_cortex_dimension(self):
        try:
            row = await self._dims("maya_rag", "novel_chunks", "embedding")
        except Exception as exc:  # noqa: BLE001 - as above
            pytest.skip(f"live store unreadable: {type(exc).__name__}: {exc}")
        if row is None:
            pytest.skip("maya_rag.novel_chunks holds no embedded row yet")

        assert row["dim"] == embed.CORTEX_EMBED_DIM
