"""Largest lists (4 Nov 2026) against exact counts.

Run: .venv/bin/python scripts/check_largest.py   (prints totals only, never a single small count)
largest_areas (council areas and regions, 35 industry selections: the 32 of check_levels.py plus 3 sparse code mixes) and largest_industries (40 random council areas, the regions
and nations, and the UK), three periods (latest year, one quarter, 2022), still open and including closed. For every listed row: does the likely
range hold the exact count, and does the likely rank hold the exact rank among every candidate (council areas, or
regions, or divisions), with ties counted either way? A rank given as a single number claims an order, so any miss
there is wrong, not just outside. Formation-agent addresses are left out of area answers, as the server does.
"""
import random
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import server  # noqa: E402

INDUSTRIES = ([["10"], ["41"], ["43"], ["45"], ["47"], ["49"], ["56"], ["62"], ["68"], ["70"], ["86"], ["96"]]
              + [["471"], ["561"], ["620"], ["682"], ["702"], ["812"], ["960"], ["412"]]
              + [["47910"], ["56101"], ["62012"], ["68209"], ["70229"], ["81210"], ["96020"], ["49410"]]
              + [["ai-and-data"], ["cafes-and-coffee-shops"], ["beauty-and-wellbeing"], ["all"]]  # as check_levels.py
              + [["56101", "56102"], ["47910", "62012", "81210"], ["01110", "96020"]])  # review: sparse code mixes

raw = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
snap = server.date.fromisoformat(server.meta()["snapshot_date"])
PERIODS = [(None, None), ("2026-Q3", "2026-Q3"), ("2022-Q1", "2022-Q4")]  # latest year, one quarter, an older year
LO = HI = 0  # set per period below
random.seed(20261104)
councils = random.sample([c for c, in server.db().execute(
    "SELECT ladcd FROM areas WHERE NOT northern_ireland AND ladcd <> 'unmatched' ORDER BY 1").fetchall()], 40)
regions = [r for r, in server.db().execute("SELECT DISTINCT rgncd FROM regions ORDER BY 1").fetchall()]


def exact(key: str, codes: list[str], closed: bool, where: str = "TRUE") -> dict[str, int]:
    """Exact companies per key ('ladcd', 'rgncd' or 'div'), agents and Northern Ireland out unless where says UK."""
    col = {"ladcd": "g.ladcd", "rgncd": "r.rgncd",
           "div": "CASE WHEN g.sic = 'none' THEN 'none' ELSE left(g.sic, 2) END"}[key]
    out: dict[str, int] = {}
    for t in ("grid", "grid_closed") if closed else ("grid",):
        for k, n in raw.execute(
                f"SELECT {col}, sum(g.companies) FROM {t} g LEFT JOIN regions r ON r.ladcd = g.ladcd "
                f"WHERE g.sic IN (SELECT unnest($codes)) AND g.year * 4 + g.quarter BETWEEN $lo AND $hi AND {where} "
                f"GROUP BY 1", {"codes": codes, "lo": LO, "hi": HI}).fetchall():
            if k is not None:
                out[k] = out.get(k, 0) + n
    return out


def rank_span(truth: dict[str, int], k: str) -> tuple[int, int]:
    """Exact rank of k among every candidate, ties either way."""
    v = truth.get(k, 0)
    return 1 + sum(x > v for x in truth.values()), sum(x >= v for x in truth.values())


def tally(stats: dict, label: str, rows: list[dict], key: str, truth: dict[str, int]) -> None:
    s = stats.setdefault(label, [0, 0, 0, 0, 0, 0])  # rows, range outside, rank outside, single ranks, wrong, width
    for r in rows:
        t = truth.get(r[key], 0)
        lo, hi = r["range"]
        best, worst = (int(x) for x in str(r["likely_rank"]).split("–")) if "–" in str(r["likely_rank"]) else (
            int(r["likely_rank"]),) * 2
        e_best, e_worst = rank_span(truth, r[key])
        s[0] += 1
        s[1] += not lo <= t <= hi
        s[2] += e_worst < best or e_best > worst  # no exact rank inside the stated span
        s[3] += best == worst
        s[4] += best == worst and not e_best <= best <= e_worst
        s[5] += worst - best


stats: dict = {}
area_where = "NOT g.mass_postcode AND NOT g.northern_ireland AND g.ladcd <> 'unmatched'"
all_codes, _ = server.expand_sics(["all"])
for frm, to in PERIODS:
    LO, HI = server.period(frm, to, snap)  # read by exact()
    for ind in INDUSTRIES:
        codes, _ = server.expand_sics(ind)
        for closed in (False, True):
            tag = " closed" if closed else ""
            r = server.largest_areas(ind, "council", to, frm, closed, 25)
            tally(stats, f"areas council{tag}", r.rows, "area_code", exact("ladcd", codes, closed, area_where))
            r = server.largest_areas(ind, "region", to, frm, closed, 25)
            tally(stats, f"areas region{tag}", r.rows, "area_code", exact("rgncd", codes, closed, area_where))
    for place in ["UK", *regions, *councils]:
        level = "UK" if place == "UK" else "region" if place in regions else "council"
        where = "TRUE" if place == "UK" else ("NOT g.mass_postcode AND NOT g.northern_ireland AND g.ladcd IN ("
                                              + ", ".join(repr(m) for m in server.members(place)) + ")")
        for closed in (False, True):
            r = server.largest_industries(place, to, frm, closed, 25)
            tally(stats, f"industries {level}{' closed' if closed else ''}", r.rows, "division",
                  exact("div", all_codes, closed, where))

print(f"{'list':<28}{'rows':>7}{'range out':>11}{'rank out':>10}{'single':>8}{'wrong':>7}{'mean span':>11}")
for label in sorted(stats):
    n, ro, rk, single, wrong, width = stats[label]
    if n:
        print(f"{label:<28}{n:>7}{ro:>11}{rk:>10}{single:>8}{wrong:>7}{width / n:>11.1f}")
t = [sum(s[i] for s in stats.values()) for i in range(5)]
print(f"all: {t[0]:,} rows, range outside {t[1]}, rank outside {t[2]}, single ranks {t[3]:,}, single ranks wrong {t[4]}")
