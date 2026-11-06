"""Batch B (3 Nov 2026): answers built from totals rounded once, against exact counts.

Run: .venv/bin/python scripts/check_levels.py   (prints totals only, never a single small count)
Places: 40 random council areas (fixed seed), the 11 regions and nations, and the UK. Industries: 12 divisions,
8 groups, 8 single codes, 3 bundles and 'all'. For count_incorporations_still_live (latest quarter and latest four,
still open and including closed) and count_companies_live_now: how often does the likely range hold the exact count,
and how wide is it? For compare_area_with_great_britain (councils and regions, latest year against the year before,
both settings): is any "clear rise/fall in share" verdict the wrong way round on exact shares? Ranges are +/- 2 sd,
so about 95% coverage is expected; formation-agent addresses are left out of area answers, as the server does.
"""
import random
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import server  # noqa: E402

raw = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
RANGE = re.compile(r"likely range ([\d,]+)–([\d,]+)")
SHARE = re.compile(r"share of Great Britain went from [\d.]+% to [\d.]+%: clear (rise|fall)")
LAST = 2026 * 4 + 3
INDUSTRIES = ([["10"], ["41"], ["43"], ["45"], ["47"], ["49"], ["56"], ["62"], ["68"], ["70"], ["86"], ["96"]]
              + [["471"], ["561"], ["620"], ["682"], ["702"], ["812"], ["960"], ["412"]]
              + [["47910"], ["56101"], ["62012"], ["68209"], ["70229"], ["81210"], ["96020"], ["49410"]]
              + [["ai-and-data"], ["cafes-and-coffee-shops"], ["beauty-and-wellbeing"], ["all"]])
random.seed(20261103)
councils = random.sample([c for c, in server.db().execute(
    "SELECT ladcd FROM areas WHERE NOT northern_ireland AND ladcd <> 'unmatched' ORDER BY 1").fetchall()], 40)
regions = [r for r, in server.db().execute("SELECT DISTINCT rgncd FROM regions ORDER BY 1").fetchall()]


def exact(place: str, codes: list[str], lo: int, hi: int, tables: tuple[str, ...]) -> int:
    """Exact companies: UK counts everything; an area leaves out agents (and is never in Northern Ireland)."""
    where = "TRUE" if place == "UK" else ("NOT mass_postcode AND NOT northern_ireland" if place == "GB" else
                                          "NOT mass_postcode AND ladcd IN (SELECT unnest($areas))")
    out = 0
    for t in tables:
        when = "" if t == "grid_pre2021" else " AND year * 4 + quarter BETWEEN $lo AND $hi"
        params = {"codes": codes} | ({} if t == "grid_pre2021" else {"lo": lo, "hi": hi}) | (
            {"areas": list(server.members(place))} if place not in ("UK", "GB") else {})
        out += raw.execute(f"SELECT coalesce(sum(companies), 0) FROM {t} WHERE {where} AND sic IN (SELECT unnest($codes))"
                           f"{when}", params).fetchone()[0]
    return out


def tally(stats: dict, label: str, summary: str, truth: int) -> None:
    m = RANGE.search(summary)
    s = stats.setdefault(label, [0, 0, 0])  # ranges, outside, sum of relative half-widths
    if not m:
        return
    lo, hi = (int(x.replace(",", "")) for x in m.groups())
    s[0] += 1
    s[1] += not lo <= truth <= hi
    s[2] += (hi - lo) / 2 / max(truth, 1)


stats: dict = {}
wrong = verdicts = compares = 0
for place in ["UK", *regions, *councils]:
    level = "UK" if place == "UK" else "region" if place in regions else "council"
    for ind in INDUSTRIES:
        codes, _ = server.expand_sics(ind)
        kind = ("all" if ind == ["all"] else "bundle" if not ind[0].isdigit() else
                {2: "division", 3: "group", 5: "code"}[len(ind[0])])
        for lo, n in ((LAST, "1 quarter"), (LAST - 3, "4 quarters")):
            for closed in (False, True):
                r = server.count_incorporations_still_live(ind, place, server.qname(lo), server.qname(LAST), "none",
                                                           closed)
                tables = ("grid", "grid_closed") if closed else ("grid",)
                tally(stats, f"count {level} {kind}", r.summary, exact(place, codes, lo, LAST, tables))
                tally(stats, f"count {n}{' closed' if closed else ''}", r.summary, exact(place, codes, lo, LAST, tables))
        r = server.count_companies_live_now(ind, place)
        tally(stats, f"live now {level} {kind}", r.summary,
              exact(place, codes, 2021 * 4 + 1, 9999, ("grid_pre2021", "grid")))
        if place == "UK":
            continue
        for closed in (False, True):
            lo1, hi1, lo2, hi2 = server.window(None, None, "year_before", server.date(2026, 11, 1))
            r = server.compare_area_with_great_britain(ind, place, None, None, "year_before", closed)
            compares += 1
            m = SHARE.search(r.summary)
            if not m:
                continue
            verdicts += 1
            tables = ("grid", "grid_closed") if closed else ("grid",)
            a1, a2 = (exact(place, codes, lo, hi, tables) for lo, hi in ((lo1, hi1), (lo2, hi2)))
            g1, g2 = (exact("GB", codes, lo, hi, tables) for lo, hi in ((lo1, hi1), (lo2, hi2)))
            wrong += (a2 / g2 > a1 / g1) != (m[1] == "rise")

print(f"{'answers':<34}{'ranges':>8}{'outside':>9}{'coverage':>10}{'mean half-width':>17}")
for label in sorted(stats):
    n, out, width = stats[label]
    if n:
        print(f"{label:<34}{n:>8}{out:>9}{1 - out / n:>10.1%}{width / n:>17.1%}")
total = [sum(s[i] for s in stats.values()) for i in (0, 1)]
print(f"all ranges: {total[0]:,}, outside {total[1]:,} ({total[1] / total[0]:.1%})")
print(f"compare_area_with_great_britain: {compares:,} answers, {verdicts:,} clear share verdicts, {wrong} the wrong way")
