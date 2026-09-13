"""Savegame pure-helper tests — QA fixes 2026-08-14 (BUG-1/2/3).

Verifies the dynamic snapshot classification and FK-safe wipe ordering
without touching the database.
"""
from core.savegame import classify_tables, fk_wipe_order, EXCLUDED_TABLES


def test_classify_session_vs_global():
    all_t = {"sessions", "ships", "ship_classes", "novel_chunks", "wiki_articles", "roll_history"}
    has_sid = {"sessions", "ships", "novel_chunks", "roll_history"}
    vec = {"novel_chunks", "wiki_articles"}
    session_scoped, global_tables = classify_tables(all_t, has_sid, vec, EXCLUDED_TABLES)
    # roll_history excluded by name, novel_chunks/wiki_articles by vector column
    assert session_scoped == ["sessions", "ships"]
    assert global_tables == ["ship_classes"]


def test_classify_global_requires_no_session_id():
    all_t = {"catalog", "state"}
    has_sid = {"state"}
    session_scoped, global_tables = classify_tables(all_t, has_sid, set(), set())
    assert session_scoped == ["state"]
    assert global_tables == ["catalog"]


def test_wipe_order_children_before_parents():
    tables = {"grandchild", "child", "parent"}
    edges = [("child", "parent"), ("grandchild", "child")]
    order = fk_wipe_order(tables, edges)
    assert order.index("grandchild") < order.index("child") < order.index("parent")


def test_wipe_order_leaf_first():
    tables = {"parent", "leaf"}
    edges = [("leaf", "parent")]
    order = fk_wipe_order(tables, edges)
    assert order[0] == "leaf"


def test_wipe_order_ignores_edges_outside_tables():
    tables = {"a", "b"}
    edges = [("a", "b"), ("a", "not_in_set")]
    order = fk_wipe_order(tables, edges)
    assert order.index("a") < order.index("b")
    assert len(order) == 2


def test_wipe_order_cycle_does_not_crash():
    tables = {"x", "y"}
    edges = [("x", "y"), ("y", "x")]
    order = fk_wipe_order(tables, edges)
    assert set(order) == tables


def test_wipe_order_no_edges_returns_all():
    tables = {"a", "b", "c"}
    order = fk_wipe_order(tables, [])
    assert set(order) == tables
