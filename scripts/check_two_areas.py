"""Batch A3 (3 Nov 2026): compare_two_areas' verdicts against exact counts.

Run: .venv/bin/python scripts/check_two_areas.py   (prints totals only, never a single small count)
Pairs: every pair of the 11 regions and nations x every 2-digit SIC division, and 400 random pairs of council areas
(fixed seed) x 12 large divisions; default period (latest four quarters against the year before), closed included.
A verdict is wrong if the exact counts point the other way: "X has more" when X's exact count isn't higher, or
"X grew faster" when X's exact share of the two together didn't rise. Also counts how often each verdict is given.
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
LO1, HI1, LO2, HI2 = 2024 * 4 + 4, 2025 * 4 + 3, 2025 * 4 + 4, 2026 * 4 + 3


def exact(area: str, d: str, lo: int, hi: int) -> int:
    return sum(raw.execute(f"""SELECT coalesce(sum(companies), 0) FROM {t} WHERE NOT mass_postcode
        AND ladcd IN (SELECT unnest(?)) AND left(sic, 2) = ? AND year * 4 + quarter BETWEEN ? AND ?""",
                           [list(server.members(area)), d, lo, hi]).fetchone()[0] for t in ("grid", "grid_closed"))


regions = [r[0] for r in server.db().execute("SELECT DISTINCT rgncd FROM regions ORDER BY 1").fetchall()]
divisions = [r[0] for r in server.db().execute("SELECT DISTINCT left(code, 2) FROM sic ORDER BY 1").fetchall()]
councils = [r[0] for r in server.db().execute("SELECT ladcd FROM areas WHERE NOT northern_ireland "
                                              "AND ladcd <> 'unmatched' ORDER BY 1").fetchall()]
rng = random.Random(20261103)
big = ["41", "43", "47", "56", "62", "68", "70", "82", "86", "96", "46", "49"]
pairs = [(a, b, d) for i, a in enumerate(regions) for b in regions[i + 1:] for d in divisions]
pairs += [(*rng.sample(councils, 2), d) for _ in range(400) for d in big]

stats = {"pairs": 0, "more given": 0, "more wrong": 0, "faster given": 0, "faster wrong": 0}
for a, b, d in pairs:
    r = server.compare_two_areas([d], a, b, None, None, "year_before", True).summary
    stats["pairs"] += 1
    na, nb = server.area_name(a), server.area_name(b)
    if " likely had more in " in r:
        stats["more given"] += 1
        says_a = f" {server.cap(na)} likely had more in " in r
        ea, eb = exact(a, d, LO2, HI2), exact(b, d, LO2, HI2)
        stats["more wrong"] += (ea <= eb) if says_a else (eb <= ea)
    if re.search(r" likely (grew faster in percentage terms|fell less in percentage terms|held steady while)", r):
        stats["faster given"] += 1
        says_a = f"so {na} likely" in r
        a1, a2, b1, b2 = exact(a, d, LO1, HI1), exact(a, d, LO2, HI2), exact(b, d, LO1, HI1), exact(b, d, LO2, HI2)
        rose = a2 * (a1 + b1) > a1 * (a2 + b2)  # a's exact share of the two together rose
        stats["faster wrong"] += (not rose) if says_a else rose
print(", ".join(f"{k}: {v:,}" for k, v in stats.items()))
