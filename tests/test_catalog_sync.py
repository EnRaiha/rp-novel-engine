"""The System's List lives in two places, so it can drift. This gate notices.

`adventures/tkg/character-sheets/galaxy-beauties.md` carries the readable list, and
`maya_rp.characters` carries the flags the engine reads. The doc is derived from the database,
and the database is what a scene is checked against, so a name in the doc that the engine has
never heard of is a real defect.

The gate checks the direction that matters: every name the doc lists, and every prisoner it
sets apart, must exist in the engine. It does not demand the reverse, because the roster
rebuild is a King decision and the imports are not on the list yet.
"""
from __future__ import annotations

import pathlib

VAULT = pathlib.Path(__file__).resolve().parents[2]
CATALOG = VAULT / "adventures/tkg/character-sheets/galaxy-beauties.md"
LIST_HEADING = "## THE SYSTEM'S LIST"
PRISONER_HEADING = "## Tahanan Pintu"
ROW = "|"


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n## ", 1)
    return rest if end == -1 else rest[:end]


def _names(section: str) -> list[str]:
    """Read the names out of a table, numbered or not.

    The list is numbered and the prisoner table is not, so a parser that demands a digit in
    the first cell silently returns nothing for the prisoners. That is exactly what the first
    version of this gate did.
    """
    names = []
    for line in section.splitlines():
        if not line.startswith(ROW):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= {"-", ":", " "}:
            continue
        first = cells[0].strip("*` ")
        header = {"nama", "name", "status", "id", "nota", "species", "degree", "beauty", "#"}
        if first.lower() in header and cells[1].strip("*` ").lower() in header:
            continue  # the table header, not a row
        name = cells[1].strip("*` ") if first.isdigit() else first
        if not name or name.lower() in header:
            continue
        names.append(name)
    return names


def _engine_names() -> set[str]:
    import psycopg2
    import os

    env = pathlib.Path.home() / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")
    conn = psycopg2.connect(host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM maya_rp.characters WHERE session_id = 5")
        return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def test_the_doc_has_a_list_and_a_prisoner_section():
    text = CATALOG.read_text(encoding="utf-8")
    assert LIST_HEADING in text, "the list heading was renamed; this gate needs updating"
    assert PRISONER_HEADING in text


def test_every_name_on_the_list_exists_in_the_engine():
    text = CATALOG.read_text(encoding="utf-8")
    listed = _names(_section(text, LIST_HEADING))
    engine = _engine_names()
    missing = [name for name in listed if name not in engine]
    assert listed, "the list parsed empty; the table format changed"
    assert not missing, f"on the list but not in the engine: {missing[:8]}"


def test_the_prisoners_are_rows_the_engine_marks_sealed():
    text = CATALOG.read_text(encoding="utf-8")
    prisoners = _names(_section(text, PRISONER_HEADING))
    assert prisoners, "the prisoner section parsed empty"
    engine = _engine_names()
    missing = [name for name in prisoners if name not in engine]
    assert not missing, f"prisoners missing from the engine: {missing}"


def test_the_list_is_sorted_by_beauty_as_the_ruling_requires():
    """D3 says women first, then beauty. The doc columns carry the beauty value."""
    text = CATALOG.read_text(encoding="utf-8")
    section = _section(text, LIST_HEADING)
    values = []
    for line in section.splitlines():
        if not line.startswith(ROW):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 5 or not cells[0].isdigit():
            continue
        try:
            values.append(float(cells[4].split("/")[0]))
        except (ValueError, IndexError):
            continue
    assert values, "no beauty values parsed"
    assert values == sorted(values, reverse=True), "the list is not in beauty order"
