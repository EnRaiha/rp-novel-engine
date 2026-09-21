# OOC ENGINE — FASA REPORT (2026-09-21)

Engine `core/ooc.py` + harness plugin + infra. This report is part of the NotebookLM bundle:
code claims resolve to `## FILE:` blocks in the sibling parts.

## 1. What shipped today

| Fasa | Isi |
|---|---|
| Fasa 3 | §6.1 suspicion consumers (`social` probe beat, `council` notice, read-only) · §6.2 `overdue` flag + `overdue_milestones()` + `latch_ruleset` via `effective_rules()` (derived from completed milestones) · §6.3 `beats_from_prose()` called by `audit()` (preview/tool never write) · §6.4 wiki module page + index + sync-pack |
| F1 fix | `effective_rules()` muted beat rules by `(trait or stage) != stage`; `ooc_rules` has no stage column, so **every seeded beat rule was dropped** and prose beats could never resolve. Muting now uses the milestone's stage. Regression: `test_seeded_shape_beat_rule_resolves_in_its_stage`. |
| Fasa 4 | enforcement §10a (pre-execute deny, recorded once, WeakSet stops double billing) · prose audit (`session/event` → `assistant/message`) · bridge loads `~/.env` (`OC_PG_*` only) when the spawning process carries none · `@deepseek-ai/dsh-session` dependency · plugin tests 34 → 40 |

## 2. Gates (all green)

```
pytest tests/test_ooc.py                    -> 57 passed
python3 -m pytest tests/ -q                 -> 227 passed
npx vitest run packages/experimental/ooc-engine -> 40 passed
npx tsc -b packages/experimental/ooc-engine/tsconfig.json -> clean
bash ~/scripts/ooc-preflight.sh             -> OK, exit 0
canon session 3: dev=0 audits=0 rpp=0 · rules=18 · milestones=4 · events=0
```

## 3. Live evidence (scratch 999)

Tool-argument turn (seam on, enforcement on): the shell call carrying
`echo 'I am sorry, I need you'` was **denied** with
`[SYSTEM] Register violation (deviation +20)` and recorded exactly once:

```
event 187: layer=tool     rule=gen-emotive-apology delta=20 dev_after=20
event 188: layer=dialogue rule=gen-emotive-apology delta=20 dev_after=40   <- prose audit
```

Earlier fasa-3 evidence: prose path completed `aloof-receive-without-answering`
(`rpp +5`, `completed_at` set) via `cli.py ooc audit`, and the bridge `turn` smoke returned
`beats_completed`. Mirror JSON always equals PG after a write.

## 4. Decisions taken

1. **Latch derives from the fired milestone** — no `ooc_system_state` column (nothing to
   drift), no `ooc_rules.enabled` flip (that would mutate campaign rules for every session).
2. **Prose path lives in `audit()`** (engine plane). The plugin's tool-arg audit and the CLI
   both flow through the engine; preview and tool layers never write.
3. **Enforcement and prose audit default OFF**; both are enabled for the canon profile by
   explicit decision. Enforcement denies tool calls, prose audit only records — penalties for
   narration stay narrative.
4. **Prose audit is CPU-only** (regex + SQL, zero tokens, no GPU).
5. **Commits are per folder/project**, not the vault root; heavy data dirs and `backups/`
   stay outside git (a live API key was found in `backups/` during the audit and never
   committed).

## 5. Current live configuration (canon)

`~/.dsh/profiles/headless/cordis.patch.yml`: sessionId 3 · The King (Aloof Commander) ·
traits `['aloof','general']` · thresholds 25/50/75 · `proseAudit: true` ·
`enforce {enabled: true, minDelta: 4}` · engine enabled with
`script: /home/maya/Bumi-Hijau/rp-engine-py/scripts/ooc_bridge.py`,
`statePath: /home/maya/.dsh/ooc/tkg-state.json`.
Backups: `cordis.patch.yml.bak-preseam-20260921-1320` (seam off).

## 6. Characters in the engine

- **Companions** (`companion_ids`): `romance_flag OR is_spouse OR bond > 0` — the only
  subjects that make a roleplay-point payment legal (O1: a companion id must appear in the
  turn's tool arguments). Canon session 3: **73 of 275** characters qualify.
- **Observer** (`observer_id`): one NPC, romance/spouse first, then bond, then importance,
  `status != 'dead'`. Canon: **id 20 Maya al-Dabaran (bond 100)** owns the suspicion meter.
- The System never notices: suspicion belongs to a mortal. Bands 25/60/90 feed
  `modules/social.py` (probe beat) and `modules/council.py` (notice).
- Known gaps: only one observer moves per session; `companion_ids` does not filter `dead`;
  `characters.traits` is unused by rule resolution.

## 7. Open items

- Izzat's dials: Q2 λ decay · Q4 (O1 vs O2) · Q5 thresholds; `proseAudit` and `enforce` are
  now ON for canon by explicit decision and can be flipped in one line each.
- Enforcement `minDelta` is 4 (any finding ≥ 4 denies a tool call).
- The plugin package is local-only inside `deepseek-harness` (untracked by policy).
