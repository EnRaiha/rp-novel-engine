#!/usr/bin/env python3
"""Embedding model registry — single source of truth (added 2026-08-14).

Standardizes the embedding model zoo. Four models were in circulation on a
6GB GTX 1060 with split vector stores. Policy:

  RP_EMBED_MODEL     nomic-embed-text  (768-dim) — RP-native: novel_chunks,
                      event/memory embeddings, stream_templates
  CORTEX_EMBED_MODEL bge-m3            (1024-dim) — cortex unified retrieval
  DEPRECATED_MODELS  bge-large, mxbai-embed-large — no new writes; vectors
                      remain readable, re-embed on touch

Any new embedding call must use one of the two active models via this
registry. Changing RP_EMBED_MODEL invalidates stored 768-dim vectors —
re-run rp_ingest_novel.py after any change.
"""
RP_EMBED_MODEL = "nomic-embed-text"
RP_EMBED_DIM = 768
CORTEX_EMBED_MODEL = "bge-m3"
CORTEX_EMBED_DIM = 1024
DEPRECATED_MODELS = {"bge-large", "mxbai-embed-large"}
