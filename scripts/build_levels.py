"""Batch B: protected totals at coarser levels, each rounded once, and companies live now.

Run: .venv/bin/python scripts/build_levels.py   (build_grid.py also runs it before exporting)
User review (3 Nov 2026): broad answers summed hundreds of separately rounded cells, so their ranges were too wide to
help (Cambridge, all industries, one quarter: about 280, likely 140-420). Each total a tool asks for now has its own
protected cell, rounded once with the same salted cell key:
  industry: a 5-digit code (or 'none'), a 3-digit group, a 2-digit division, or 'all'
  place: a council area (or 'unmatched'), a region or nation, 'GB' (no agents, no Northern Ireland), or 'UK' (all)
p_agg holds every pair per quarter (copies of p_area and p_uk for council x code and UK x code, so those keep their
values), p_agg_closed the same by age, p_agg_gone the same for closures by dissolution quarter, p_pre2021 the companies registered before 2021 still live in the snapshot (live
now = these plus every quarter since), and p_pre2021_mass their agent-address cells. A new total is rounded on its own
only when its parts' shown values add up to INDEPENDENT or more (see below). Parts no longer add up exactly to totals;
answers say so. check() runs pin_levels over every add-up relation and fails the build if any count below 10 can be
pinned to one value.
"""
import os
import sys
from pathlib import Path

import duckdb

import pin_levels

ROOT = Path(__file__).resolve().parent.parent
GRID = ROOT / "data/grid.duckdb"
# ONS Local Authority District to Region (April 2025) Lookup in EN (V2), downloaded 3 Nov 2026, sha256 ef8470fe...
REGIONS = ROOT / "data/lookup/regions/LAD25_RGN25_EN_LU_v2.csv"
GEO = {  # place level: (column expression, filter)
    "council": ("ladcd", "NOT mass AND NOT ni"),
    "region": ("rgncd", "NOT mass AND NOT ni AND rgncd IS NOT NULL"),
    "gb": ("'GB'", "NOT mass AND NOT ni"),
    "uk": ("'UK'", "TRUE"),
}
IND = {  # industry level: (column expression, filter)
    "code": ("sic", "TRUE"),
    "group": ("left(sic, 3)", "sic <> 'none'"),
    "division": ("left(sic, 2)", "sic <> 'none'"),
    "all": ("'all'", "TRUE"),
}


def cell_key_salt() -> str:
    """Secret salt for the protected column, read from .env (never printed)."""
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("MARKET_PULSE_CELL_KEY_SALT="):
            os.environ.setdefault("MARKET_PULSE_CELL_KEY_SALT", line.split("=", 1)[1].strip())
    salt = os.environ.get("MARKET_PULSE_CELL_KEY_SALT", "")
    if len(salt) < 32:
        raise SystemExit("MARKET_PULSE_CELL_KEY_SALT missing or too short in .env")
    return salt


def rounded(table: str, key: str) -> str:
    """The cell-key rounding used for every p_* table: up to the next 5 with probability (n mod 5) / 5."""
    return (f"(n - n % 5 + CASE WHEN md5_number(concat_ws('|', $salt, '{table}', {key})) % 5 < n % 5 "
            f"THEN 5 ELSE 0 END)::INTEGER AS protected")


def build_regions(con) -> None:
    """Which council areas each region covers: England's 9 from the ONS lookup, Wales and Scotland as wholes."""
    con.execute(f"""CREATE OR REPLACE TABLE regions AS
        SELECT RGN25CD AS rgncd, RGN25NM AS rgnnm, LAD25CD AS ladcd FROM read_csv('{REGIONS}', all_varchar=true)
        UNION ALL SELECT 'W92000004', 'Wales', ladcd FROM areas WHERE ladcd LIKE 'W%'
        UNION ALL SELECT 'S92000003', 'Scotland', ladcd FROM areas WHERE ladcd LIKE 'S%'""")


# A new total is rounded on its own only if its parts' shown values add up to at least INDEPENDENT; otherwise it is
# published as that sum. Independent rounding of every level narrowed about 1.7 million small cells (pin_levels; the
# old tables narrowed about 11,600) because small totals sat on small parts; a total built from its parts' shown
# values adds no constraint. The rule reads only published values, so whether a total is rounded on its own
# reveals nothing new. The server treats a cell shown at INDEPENDENT or more as one rounded cell, and anything smaller
# as the sum of every part under it (its range is then as wide as before).
INDEPENDENT = 50
STEPS = [  # (place level, industry level, children: 'ind' = same place, industry one level down; 'geo' = places in it)
    ("council", "group", "ind"), ("council", "division", "ind"), ("council", "all", "ind"),
    ("uk", "group", "ind"), ("uk", "division", "ind"), ("uk", "all", "ind"),
    *((g, i, "geo") for g in ("region", "gb") for i in ("code", "group", "division", "all")),
]
CHILD = {"group": "code", "division": "group", "all": "division"}
PARENT_IND = {"group": "left(ind, 3)", "division": "left(ind, 2)", "all": "'all'"}


def build_tables(con, salt: str) -> None:
    for source, table, time, base in (("grid", "p_agg", "year, quarter", "p_area"),
                                      ("grid_closed", "p_agg_closed", "year, quarter, age", "p_area"),
                                      ("grid_gone", "p_agg_gone", "year, quarter", "p_area"),
                                      ("grid_pre2021", "p_pre2021", "", None)):
        if source == "grid_pre2021" and not con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = 'grid_pre2021'").fetchone()[0]:
            print("grid_pre2021 missing: rebuild with build_grid.py for live-now counts")
            continue
        cols = f"{', ' + time if time else ''}"
        on = "".join(f" AND r.{c} = s.{c}" for c in time.split(", ") if c)
        con.execute(f"""CREATE OR REPLACE TEMP VIEW b AS SELECT g.ladcd, r.rgncd, g.northern_ireland AS ni,
            g.mass_postcode AS mass, g.sic{cols}, g.companies FROM {source} g LEFT JOIN regions r USING (ladcd)""")
        con.execute(f"CREATE OR REPLACE TEMP TABLE raw AS " + " UNION ALL ".join(
            f"""SELECT '{gl}' AS gl, '{il}' AS il, {g} AS geo, {i} AS ind{cols}, sum(companies)::INTEGER AS n
                FROM b WHERE {gf} AND {f} GROUP BY ALL"""
            for gl, (g, gf) in GEO.items() for il, (i, f) in IND.items()))
        con.execute(f"CREATE OR REPLACE TEMP TABLE pub (gl VARCHAR, il VARCHAR, geo VARCHAR, ind VARCHAR"
                    + "".join(f", {c} {'VARCHAR' if c == 'age' else 'INTEGER'}" for c in time.split(", ") if c)
                    + ", protected INTEGER)")
        sfx = table.removeprefix("p_agg") if base else ""
        if base:  # council x code and UK x code keep their published values
            con.execute(f"INSERT INTO pub SELECT 'council', 'code', ladcd, sic{cols}, protected FROM {base}{sfx}")
            con.execute(f"INSERT INTO pub SELECT 'uk', 'code', 'UK', sic{cols}, protected FROM p_uk{sfx}")
        else:  # before 2021: every council x code and UK x code cell is new
            con.execute(f"""INSERT INTO pub SELECT gl, il, geo, ind{cols}, {rounded(table, "geo, ind" + cols)}
                            FROM raw WHERE il = 'code' AND gl IN ('council', 'uk')""", {"salt": salt})
        for gl, il, kind in STEPS:
            if kind == "ind":
                kids = f"""SELECT geo, {PARENT_IND[il]} AS ind{cols}, sum(protected) AS s FROM pub
                           WHERE gl = '{gl}' AND il = '{CHILD[il]}' {"AND ind <> 'none'" if il != 'all' else ''} GROUP BY ALL"""
                if il == "all":  # 'all' = the divisions plus 'none'
                    kids = kids.replace(f"il = '{CHILD[il]}' ", f"(il = 'division' OR (il = 'code' AND ind = 'none')) ")
            else:  # a region = its council areas; GB = the regions plus 'unmatched'
                below = ("SELECT r.rgncd AS geo, p.* EXCLUDE (geo) FROM pub p JOIN regions r ON p.geo = r.ladcd "
                         "WHERE p.gl = 'council'") if gl == "region" else (
                         "SELECT 'GB' AS geo, p.* EXCLUDE (geo) FROM pub p WHERE p.gl = 'region' "
                         "OR (p.gl = 'council' AND p.geo = 'unmatched')")
                kids = f"SELECT geo, ind{cols}, sum(protected) AS s FROM ({below}) WHERE il = '{il}' GROUP BY ALL"
            con.execute(f"""INSERT INTO pub SELECT r.gl, r.il, r.geo, r.ind{cols.replace(', ', ', r.')},
                    CASE WHEN coalesce(s.s, 0) >= {INDEPENDENT} THEN
                         (r.n - r.n % 5 + CASE WHEN md5_number(concat_ws('|', $salt, '{table}', r.geo, r.ind{cols.replace(', ', ', r.')})) % 5
                                              < r.n % 5 THEN 5 ELSE 0 END)
                         ELSE coalesce(s.s, 0) END::INTEGER
                FROM raw r LEFT JOIN ({kids}) s ON r.geo = s.geo AND r.ind = s.ind{on}
                WHERE r.gl = '{gl}' AND r.il = '{il}'""", {"salt": salt})
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT geo, ind{cols}, protected FROM pub")
        if not base:
            con.execute(f"""CREATE OR REPLACE TABLE p_pre2021_mass AS SELECT ladcd, sic, {rounded('p_pre2021_mass', 'ladcd, sic')}
                FROM (SELECT ladcd, sic, sum(companies)::INTEGER AS n FROM b WHERE mass AND NOT ni GROUP BY ALL)""",
                        {"salt": salt})
        own = con.execute(f"SELECT count(*) FILTER (WHERE protected >= {INDEPENDENT}) FROM pub WHERE NOT "
                          "(il = 'code' AND gl IN ('council', 'uk'))").fetchone()[0]
        print(f"{table}: {con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:,} cells, {own:,} new totals "
              f"shown at {INDEPENDENT} or more")


LINK_LAST = 2025 * 4 + 3  # registered by 2025-Q3 and dissolved within a year: gone by 2026-Q3, the last closures quarter


def family(con, sfx: str) -> None:
    """Load one family ('': open with before-2021, '_closed', or '_gone') into pin_levels' cell and edge tables, in SQL."""
    age = "age" if sfx == "_closed" else "NULL"
    parts = [f"SELECT 'a' AS k, geo, ind, concat_ws('|', year, quarter, {age}) AS sl, protected AS p FROM p_agg{sfx}",
             f"SELECT 'm', ladcd, sic, concat_ws('|', year, quarter, {age}), protected FROM p_mass{sfx}"]
    if not sfx and con.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'p_pre2021'").fetchone()[0]:
        parts += ["SELECT 's', geo, ind, 'pre2021', protected FROM p_pre2021",
                  "SELECT 'sm', ladcd, sic, 'pre2021', protected FROM p_pre2021_mass"]
    con.execute(f"""CREATE OR REPLACE TEMP TABLE cell AS
        SELECT row_number() OVER () AS id, c.*,
            CASE WHEN geo = 'UK' THEN 'uk' WHEN geo = 'GB' THEN 'gb' WHEN geo IN (SELECT rgncd FROM regions) THEN 'region'
                 ELSE 'council' END AS gl,
            CASE WHEN ind = 'all' THEN 'all' WHEN ind = 'none' OR len(ind) = 5 THEN 'code'
                 WHEN len(ind) = 3 THEN 'group' ELSE 'division' END AS il,
            CASE WHEN k IN ('a', 's') AND ind <> 'all' THEN CASE WHEN ind = 'none' OR len(ind) = 2 THEN 'all'
                 WHEN len(ind) = 5 THEN left(ind, 3) ELSE left(ind, 2) END END AS up_ind,
            CASE WHEN k IN ('a', 's') AND geo <> 'UK' THEN CASE WHEN geo = 'GB' THEN 'UK'
                 WHEN geo = 'unmatched' OR geo IN (SELECT rgncd FROM regions) THEN 'GB'
                 ELSE (SELECT rgncd FROM regions r WHERE r.ladcd = c.geo) END END AS up_geo
        FROM ({" UNION ALL ".join(parts)}) c""")
    con.execute("""CREATE OR REPLACE TEMP TABLE edge AS
        SELECT p.id AS parent, 'ind' AS kind, c.id AS kid, false AS slack FROM cell c
            JOIN cell p ON p.k = c.k AND p.geo = c.geo AND p.ind = c.up_ind AND p.sl = c.sl
        UNION ALL
        SELECT p.id, CASE WHEN p.geo = 'UK' THEN 'uk' ELSE 'geo' END, c.id, p.geo = 'UK' FROM cell c
            JOIN cell p ON p.k = c.k AND p.geo = c.up_geo AND p.ind = c.ind AND p.sl = c.sl
        UNION ALL  -- UK = GB + agent cells + NI
        SELECT u.id, 'uk', m.id, true FROM cell u JOIN cell m ON m.k = CASE u.k WHEN 'a' THEN 'm' ELSE 'sm' END
            AND m.sl = u.sl AND (u.ind = 'all' OR (u.ind = 'none' AND m.ind = 'none')
                                 OR (u.ind <> 'none' AND m.ind <> 'none' AND starts_with(m.ind, u.ind)))
            WHERE u.k IN ('a', 's') AND u.geo = 'UK'""")
    # Which totals were rounded on their own: the base cells (council x code, UK x code, agent cells), and a new total
    # whose parts' shown values (along the relation it was built from) add up to INDEPENDENT or more. The rest must
    # equal that sum exactly, which checks the build.
    con.execute(f"""CREATE OR REPLACE TEMP TABLE built AS SELECT e.parent AS id, sum(c.p) AS s FROM edge e
        JOIN cell c ON c.id = e.kid JOIN cell p ON p.id = e.parent
        WHERE e.kind = CASE WHEN p.gl IN ('council', 'uk') THEN 'ind' ELSE 'geo' END
          AND NOT (p.il = 'code' AND p.gl IN ('council', 'uk')) GROUP BY ALL""")
    con.execute(f"""ALTER TABLE cell ADD COLUMN own BOOLEAN;
        UPDATE cell SET own = coalesce((SELECT b.s >= {INDEPENDENT} FROM built b WHERE b.id = cell.id), true)""")
    bad = con.execute("SELECT count(*) FROM cell JOIN built b USING (id) WHERE NOT own AND p <> b.s").fetchone()[0]
    if bad:
        raise SystemExit(f"{bad:,} totals below {INDEPENDENT} are not the sum of their parts' shown values")


def links(con) -> None:
    """Closed and closures hold the same companies, so check them together (privacy review, 5 Nov 2026). A company
    registered in quarter q and dissolved within a year is in closed under_1y at q and in closures in q to q + 4, so for
    any run of quarters a to b: closed under_1y a..b <= closures a..b + 4. Nothing else ties them: 1y_plus and later
    registrations can reach October, which closures stop short of and nothing publishes, and closures hold companies
    registered before 2021. Each such limit is a slack relation over a stand-in total (cell k = 'w') of the closures
    window, at every level of the tables. A limit that can't bind on the families' own ranges never will, so it is left
    out: ranges only tighten.
    These limits are the client's best case, not facts about every cell: a few companies changed postcode between the
    two downloads or dropped out of the later one (closures_check.py), so a real limit may be loose by those companies.
    Propagation is monotone, so stricter limits can only give narrower ranges: anything a client could pin with the
    real limits shows here as a pin or an empty range, and both stop the build. A narrowed count here may overstate."""
    for sfx in ("_closed", "_gone"):
        family(con, sfx)
        pin_levels.start(con)
        pin_levels.propagate(con)
        con.execute(f"CREATE OR REPLACE TEMP TABLE cell_{sfx[1:]} AS SELECT * FROM cell")
        con.execute(f"CREATE OR REPLACE TEMP TABLE edge_{sfx[1:]} AS SELECT * FROM edge")
    shift = con.execute("SELECT max(id) FROM cell_closed").fetchone()[0]
    con.execute(f"""CREATE OR REPLACE TEMP TABLE cell AS
        SELECT id, k, geo, ind, sl, p, own, lo, hi, 'closed' AS fam FROM cell_closed
        UNION ALL SELECT id + {shift}, k, geo, ind, sl, p, own, lo, hi, 'gone' FROM cell_gone""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE edge AS SELECT * FROM edge_closed
        UNION ALL SELECT parent + {shift}, kind, kid + {shift}, slack FROM edge_gone""")
    time = "split_part(sl, '|', 1)::INT * 4 + split_part(sl, '|', 2)::INT"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE u AS SELECT id, k, geo, ind, {time} AS t, hi,
            sum(hi) OVER (PARTITION BY k, geo, ind ORDER BY {time}) AS run
        FROM cell WHERE fam = 'closed' AND sl LIKE '%|under_1y' AND {time} <= {LINK_LAST}""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE g AS SELECT id, k, geo, ind, {time} AS t, lo
        FROM cell WHERE fam = 'gone'""")
    con.execute(f"""CREATE OR REPLACE TEMP TABLE w AS
        SELECT row_number() OVER () + (SELECT max(id) FROM cell) AS id, * FROM (
            SELECT a.k, a.geo, a.ind, a.t AS a, b.t AS b, b.run - a.run + a.hi AS most, coalesce(sum(g.lo), 0) AS least
            FROM u a JOIN u b ON a.k = b.k AND a.geo = b.geo AND a.ind = b.ind AND b.t >= a.t
            LEFT JOIN g ON g.k = a.k AND g.geo = a.geo AND g.ind = a.ind AND g.t BETWEEN a.t AND b.t + 4
            GROUP BY ALL HAVING most > least)""")
    con.execute(f"""INSERT INTO cell SELECT id, 'w', geo, ind, concat_ws('|', a, b), 0, false, 0, {pin_levels.BIG}, 'link' FROM w""")
    con.execute("""INSERT INTO edge
        SELECT w.id, 'wg', g.id, false FROM w JOIN g ON g.k = w.k AND g.geo = w.geo AND g.ind = w.ind
            AND g.t BETWEEN w.a AND w.b + 4
        UNION ALL
        SELECT w.id, 'wc', u.id, true FROM w JOIN u ON u.k = w.k AND u.geo = w.geo AND u.ind = w.ind
            AND u.t BETWEEN w.a AND w.b""")
    # a window with no closures cell at all holds none
    con.execute("UPDATE cell SET hi = 0 WHERE k = 'w' AND id NOT IN (SELECT parent FROM edge WHERE kind = 'wg')")
    rounds = pin_levels.propagate(con)
    pinned, narrowed = pin_levels.results(con)
    n, e, c = (con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("cell", "edge", "w"))
    counts = con.execute(f"""SELECT count(*) FILTER (WHERE k <> 'w' AND {pinned}), count(*) FILTER (WHERE {narrowed}) FROM cell""").fetchone()
    print(f"pin check (closed with closures): {n:,} cells, {e:,} links, {c:,} limits that could bind, {rounds} rounds; "
          f"{counts[0]} pinned, {counts[1]:,} small cells narrowed but not pinned")
    if counts[0]:
        # identifiers only, as in check()
        print("  e.g.", con.execute(f"SELECT fam, k, geo, ind, sl FROM cell WHERE k <> 'w' AND {pinned} LIMIT 5").fetchall())
        raise SystemExit(f"{counts[0]} small counts pinned across closed and closures: not published")


def check(con) -> None:
    con.execute("SET memory_limit = '4GB'")
    failed = 0
    for sfx, label in (("", "open and before 2021"), ("_closed", "closed"), ("_gone", "closures")):
        family(con, sfx)
        pin_levels.start(con)
        rounds = pin_levels.propagate(con)
        pinned, narrowed = pin_levels.results(con)
        n, e = (con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("cell", "edge"))
        counts = con.execute(f"SELECT count(*) FILTER (WHERE {pinned}), count(*) FILTER (WHERE {narrowed}) FROM cell").fetchone()
        print(f"pin check ({label}): {n:,} cells, {e:,} links, {rounds} rounds; "
              f"{counts[0]} pinned, {counts[1]:,} small cells narrowed but not pinned")
        for row in con.execute(f"""SELECT k, gl, il, count(*) FILTER (WHERE {pinned}) AS pinned,
                count(*) FILTER (WHERE {narrowed}) AS narrowed FROM cell GROUP BY ALL
                HAVING pinned + narrowed > 0 ORDER BY narrowed DESC""").fetchall():
            print("  ", *row)
        if counts[0]:
            # identifiers only: a pinned cell's range is its exact small count, which mustn't reach a log
            print("  e.g.", con.execute(f"SELECT k, geo, ind, sl FROM cell WHERE {pinned} LIMIT 5").fetchall())
        failed += counts[0]
    if failed:
        raise SystemExit(f"{failed} small counts pinned: not published")
    links(con)


if __name__ == "__main__":
    con = duckdb.connect(str(GRID))
    build_regions(con)
    build_tables(con, cell_key_salt())
    check(con)
    con.close()
    sys.exit(0)
