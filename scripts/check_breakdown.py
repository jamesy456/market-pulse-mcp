"""Batch A4 (3 Nov 2026): breakdown_by_industry's verdicts against exact counts.

Run: .venv/bin/python scripts/check_breakdown.py   (prints totals only, never a single small count)
Places: the UK, the 11 regions and nations, and every GB council area, in two settings: the default (latest four
quarters against the year before, closed included) and 2026-Q1 to Q3 against the three quarters just before, still
open only. A verdict is wrong if the exact counts moved the other way (or not at all): "likely rose" when the exact
count didn't rise, and so on, for each division row, its great_britain column and the total.
Limits (review codex-breakdown): this checks only that stated directions are right. It doesn't count real changes the
test missed, or check how often the test would fire by chance.
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import server  # noqa: E402

raw = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
SETTINGS = [((None, None, "year_before", True), (2024 * 4 + 4, 2025 * 4 + 3, 2025 * 4 + 4, 2026 * 4 + 3)),
            (("2026-Q3", "2026-Q1", "previous", False), (2025 * 4 + 2, 2025 * 4 + 4, 2026 * 4 + 1, 2026 * 4 + 3))]


def exact(where: str, params: list, lo: int, hi: int) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in ("grid", "grid_closed") if CLOSED else ("grid",):
        for d, n in raw.execute(f"""SELECT CASE WHEN sic = 'none' THEN 'none' ELSE left(sic, 2) END, sum(companies)
                FROM {t} WHERE {where} AND year * 4 + quarter BETWEEN ? AND ? GROUP BY 1""", [*params, lo, hi]).fetchall():
            out[d] = out.get(d, 0) + n
    return out


def wrong(v: str, a: int, b: int) -> bool:
    return (b <= a) if v == "likely rose" else (b >= a)


AREA = "NOT mass_postcode AND ladcd IN (SELECT unnest(?))"
regions = [r[0] for r in server.db().execute("SELECT DISTINCT rgncd FROM regions ORDER BY 1").fetchall()]
councils = [r[0] for r in server.db().execute("SELECT ladcd FROM areas WHERE NOT northern_ireland "
                                              "AND ladcd <> 'unmatched' ORDER BY 1").fetchall()]
stats = {"places": 0, "rows": 0, "verdicts": 0, "wrong": 0, "gb verdicts": 0, "gb wrong": 0,
         "total verdicts": 0, "total wrong": 0}
for (to_q, from_q, against, CLOSED), (LO1, HI1, LO2, HI2) in SETTINGS:
    gb = [exact("NOT mass_postcode AND NOT northern_ireland", [], lo, hi) for lo, hi in ((LO1, HI1), (LO2, HI2))]
    for place in ["UK", *regions, *councils]:
        r = server.breakdown_by_industry(place, to_q, from_q, against, CLOSED)
        where, params = ("TRUE", []) if place == "UK" else (AREA, [list(server.members(place))])
        e1, e2 = (exact(where, params, lo, hi) for lo, hi in ((LO1, HI1), (LO2, HI2)))
        stats["places"] += 1
        for row in r.rows:
            d = row["division"]
            stats["rows"] += 1
            if row["verdict"].startswith("likely"):
                stats["verdicts"] += 1
                stats["wrong"] += wrong(row["verdict"], e1.get(d, 0), e2.get(d, 0))
            if row.get("great_britain", "").startswith("likely"):
                stats["gb verdicts"] += 1
                stats["gb wrong"] += wrong(row["great_britain"], gb[0].get(d, 0), gb[1].get(d, 0))
        for v in ("more", "fewer"):
            if f": likely {v} (" in r.summary:
                stats["total verdicts"] += 1
                stats["total wrong"] += wrong("likely rose" if v == "more" else "likely fell",
                                              sum(e1.values()), sum(e2.values()))
print(", ".join(f"{k}: {v:,}" for k, v in stats.items()))
