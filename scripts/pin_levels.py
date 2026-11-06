"""Batch B pin check: can any combination of published cells pin a count below 10 to one value?

Generalises pin_check.py (one UK = areas + agents + NI relation per code and quarter) to every add-up relation the
published tables now share. A cell rounded on its own ('own') shown p has its true count in [max(0, p - 4), p + 4]; a
total published as the sum of its parts' shown values carries no range of its own (it starts at [0, unbounded]).
Relations, each a row group in edge(parent, kind, kid, slack):
  ind: a 3-digit group = its codes; a division = its groups; 'all' = the divisions plus 'none'
  geo: a region = its council areas; GB = the regions plus 'unmatched'
  uk: UK = GB + agent cells + NI (unknown, >= 0, so slack)
Before-2021 cells (live now = these plus every quarter since) share no relation with the quarterly ones: a live-now
table overlapping them pinned 21 small counts (3 Nov 2026).
Interval propagation runs in DuckDB to a fixed point over every relation at once (a cell is in several). The first
version was a Python worklist that re-summed a relation's parts whenever one part changed: quadratic on the UK totals,
it ran 2.5 hours and 9 GB without finishing (3 Nov 2026). A pinned cell fails the build; narrowed-but-not-pinned cells
are counted (the accepted residual of rounding overlapping tables, as with ONS cell-key tables). Absent cells are true
zeros and are left out of every sum, which assumes the client knows more than it does, so the check errs safe.
"""
import duckdb

BIG = 10**9  # stands in for "no upper bound"
SMALL = 10


def propagate(con, max_rounds: int = 1000) -> int:
    """Tighten cell(id, lo, hi) in place over edge(parent, kind, kid, slack) until a round changes nothing.
    Each round applies every relation to the current ranges at once; each step is a sound inference, so the fixed
    point is the same as one relation at a time. Returns the number of rounds."""
    for n in range(1, max_rounds + 1):
        # Unbounded parts are counted, not summed: a sum with one is unbounded, and a part's lower bound only moves
        # when every other part in the relation is bounded.
        con.execute(f"""CREATE OR REPLACE TEMP TABLE sums AS
            SELECT e.parent, e.kind, bool_or(e.slack) AS slack, sum(c.lo) AS s_lo,
                   sum(c.hi) FILTER (WHERE c.hi < {BIG}) AS fin, count(*) FILTER (WHERE c.hi >= {BIG}) AS n_inf
            FROM edge e JOIN cell c ON c.id = e.kid GROUP BY e.parent, e.kind""")
        changed = con.execute(f"""UPDATE cell SET lo = greatest(cell.lo, b.lo), hi = least(cell.hi, b.hi)
            FROM (SELECT id, max(lo) AS lo, min(hi) AS hi FROM (
                    SELECT parent AS id, s_lo AS lo, CASE WHEN slack OR n_inf > 0 THEN {BIG} ELSE fin END AS hi FROM sums
                    UNION ALL
                    SELECT e.kid,
                           CASE WHEN s.slack OR s.n_inf - (k.hi >= {BIG})::INT > 0 THEN 0
                                ELSE p.lo - (coalesce(s.fin, 0) - CASE WHEN k.hi < {BIG} THEN k.hi ELSE 0 END) END,
                           p.hi - (s.s_lo - k.lo)
                    FROM edge e JOIN sums s ON s.parent = e.parent AND s.kind = e.kind
                    JOIN cell p ON p.id = e.parent JOIN cell k ON k.id = e.kid)
                  GROUP BY id) b
            WHERE cell.id = b.id AND (b.lo > cell.lo OR b.hi < cell.hi)""").fetchone()[0]
        if not changed:
            return n
    raise SystemExit(f"pin check did not settle in {max_rounds} rounds")


def start(con) -> None:
    """Initial ranges on cell(id, p, own): own cells [max(0, p - 4), p + 4], sums of parts unbounded."""
    con.execute(f"""ALTER TABLE cell ADD COLUMN lo BIGINT; ALTER TABLE cell ADD COLUMN hi BIGINT;
        UPDATE cell SET lo = CASE WHEN own THEN greatest(0, p - 4) ELSE 0 END,
                        hi = CASE WHEN own THEN p + 4 ELSE {BIG} END""")


def results(con):
    """(pinned, narrowed) where clause pieces, after propagate. Pinned: a count that could be below 10 has one value
    left. Narrowed: an own cell that could be below 10 lost some values but not all."""
    if con.execute("SELECT count(*) FROM cell WHERE lo > hi").fetchone()[0]:
        raise SystemExit("pin check: a range came out empty, so the relations or the build are wrong")
    pinned = "lo = hi AND CASE WHEN own THEN greatest(0, p - 4) < 10 ELSE lo < 10 END"
    narrowed = "own AND greatest(0, p - 4) < 10 AND lo < hi AND (lo > greatest(0, p - 4) OR hi < p + 4)"
    return pinned, narrowed


def check(cells: dict, constraints: list, unknown=()) -> tuple[list, list]:
    """Small in-memory version for the self-tests. cells: name -> shown value; constraints: (parent, [kids], slack);
    unknown: names published as the sum of their parts. Returns (pinned, narrowed) as (name, shown, [lo, hi])."""
    con = duckdb.connect()
    ids = {k: i for i, k in enumerate(cells)}
    con.execute("CREATE TEMP TABLE cell (id BIGINT, name VARCHAR, p BIGINT, own BOOLEAN)")
    con.executemany("INSERT INTO cell VALUES (?, ?, ?, ?)", [(ids[k], k, p, k not in unknown) for k, p in cells.items()])
    con.execute("CREATE TEMP TABLE edge (parent BIGINT, kind VARCHAR, kid BIGINT, slack BOOLEAN)")
    con.executemany("INSERT INTO edge VALUES (?, ?, ?, ?)", [(ids[p], str(i), ids[k], s)
                                                             for i, (p, kids, s) in enumerate(constraints) for k in kids])
    start(con)
    propagate(con)
    pinned, narrowed = results(con)
    rows = lambda w: [(n, p, [lo, hi]) for n, p, lo, hi in con.execute(f"SELECT name, p, lo, hi FROM cell WHERE {w}").fetchall()]
    return rows(pinned), rows(narrowed)


if __name__ == "__main__":
    # pin_check.py's scenario: UK shows 0, four cells show 5 each, NI unknown -> each pinned to exactly 1.
    pinned, _ = check({"uk": 0, "a": 5, "b": 5, "c": 5, "d": 5}, [("uk", ["a", "b", "c", "d"], True)])
    assert sorted(k for k, *_ in pinned) == ["a", "b", "c", "d", "uk"], pinned  # cells 1 each, UK 4
    # Two levels: a division of two groups shown 10 and 0, groups made of codes shown 5 and 5 -> codes not pinned.
    pinned, narrowed = check({"d": 10, "g1": 10, "g2": 0, "c1": 5, "c2": 5},
                             [("d", ["g1", "g2"], False), ("g1", ["c1", "c2"], False)])
    assert not pinned
    # Two roundings of one value never pin it: a parent with a single child.
    for p, c in ((5, 0), (0, 5), (5, 5), (10, 5), (5, 10)):
        assert not check({"p": p, "c": c}, [("p", ["c"], False)])[0]
    # A total published as the sum of its parts' shown values tells nothing new, even with a single part.
    for kids in (["a"], ["a", "b"], ["a", "b", "c", "d"]):
        cells = {"p": 5 * len(kids), **{k: 5 for k in kids}}
        assert check(cells, [("p", kids, False)], unknown={"p"}) == ([], []), kids
    # A total rounded on its own does narrow: shown 0 (0-4) over parts shown 5 and 5 (1-9 each) -> parts 1-3, total 2-4.
    _, narrowed = check({"p": 0, "a": 5, "b": 5}, [("p", ["a", "b"], False)])
    assert sorted((k, r) for k, _, r in narrowed) == [("a", [1, 3]), ("b", [1, 3]), ("p", [2, 4])], narrowed
    # Slack (UK = parts + NI >= 0) only caps the parts: UK shown 0 (0-4) over a part shown 5 -> both 1-4.
    pinned, narrowed = check({"uk": 0, "a": 5}, [("uk", ["a"], True)])
    assert not pinned and sorted((k, r) for k, _, r in narrowed) == [("a", [1, 4]), ("uk", [1, 4])], narrowed
    # Unbounded parts: two of them under a total shown 10 learn nothing about their lower bounds; a sum-of-parts total
    # in the middle of a chain passes the top total's limit down (top 0, middle = parts 5 + 5 -> parts 1-3).
    con_test = check({"t": 10, "u1": 0, "u2": 0}, [("t", ["u1", "u2"], False)], unknown={"u1", "u2"})
    assert con_test == ([], []), con_test
    pinned, narrowed = check({"t": 0, "m": 10, "a": 5, "b": 5}, [("t", ["m"], False), ("m", ["a", "b"], False)],
                             unknown={"m"})
    assert sorted((k, r) for k, _, r in narrowed) == [("a", [1, 3]), ("b", [1, 3]), ("t", [2, 4])], (pinned, narrowed)
    # A limit between families (build_levels.links): a stand-in total w of a closures window caps a closed cell.
    # Closed shown 10 (6-14) within a window of one closures cell shown 5 (1-9): both 6-9.
    _, narrowed = check({"w": 0, "g": 5, "c": 10}, [("w", ["g"], False), ("w", ["c"], True)], unknown={"w"})
    assert sorted((k, r) for k, _, r in narrowed) == [("c", [6, 9]), ("g", [6, 9])], narrowed
    print("pin_levels self-test ok")
