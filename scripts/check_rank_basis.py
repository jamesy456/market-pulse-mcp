"""Final review, 5 Nov 2026: does the hotspot ranking name areas whose rise is only that older companies have closed?

Run: .venv/bin/python -u scripts/check_rank_basis.py   (prints totals only, no small counts)
Every 2-digit division and all industries, four periods, both directions. Each area the ranking names is checked on
exact counts, with dissolved companies counted: same direction past the same bar (exact z, no rounding allowance).
Also prints the busiest quarter of each year, which backs the server's seasonal note.
"""
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import server  # noqa: E402
from release import share_z, z_needed  # noqa: E402

raw = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
DIVISIONS = [c for c, in raw.execute("SELECT DISTINCT left(sic, 2) FROM grid WHERE sic <> 'none' ORDER BY 1").fetchall()]
SELECTIONS = [["all"]] + [[d] for d in DIVISIONS]


def exact(sics, lo, hi) -> dict:
    """Registered in the period, dissolved since included: every area in Great Britain, agents left out."""
    wanted = "" if sics == ["all"] else "AND left(sic, 2) = ?"
    args = [] if sics == ["all"] else sics
    sql = (f"SELECT ladcd, sum(companies) FROM {{t}} WHERE NOT mass_postcode AND NOT northern_ireland {wanted} "
           "AND year * 4 + quarter BETWEEN ? AND ? GROUP BY ladcd")
    out: dict = {}
    for t in ("grid", "grid_closed"):
        for c, v in raw.execute(sql.format(t=t), [*args, lo, hi]).fetchall():
            out[c] = out.get(c, 0) + int(v)
    return out


def q(s: str) -> int:
    return int(s[:4]) * 4 + int(s[-1])


seen: dict = {}


def run(closed: bool) -> None:
    named = held = wrong = total_tested = 0
    per_period: dict = {}
    for sics in SELECTIONS:
        for to in ("2026-Q3", "2025-Q3", "2024-Q3", "2023-Q3"):
            k2 = q(to)
            e1, e2 = exact(sics, k2 - 7, k2 - 4), exact(sics, k2 - 3, k2)
            g1, g2 = sum(e1.values()), sum(e2.values())
            for direction in ("growing", "shrinking"):
                res = server.rank_areas_against_great_britain(sics, direction, to, 25, include_closed=closed)
                tests = int(re.search(r"for all (\d+) areas", res.summary)[1]) if "for all" in res.summary else 350
                tested = re.search(r"Of the (\d+) tested", res.summary)
                total_tested += int(tested[1]) if tested else 0
                for row in res.rows:
                    a, b = e1.get(row["area_code"], 0), e2.get(row["area_code"], 0)
                    z = share_z(a, g1, b, g2) if min(a, b) >= 10 else 0.0
                    signed = z if direction == "growing" else -z
                    named += 1
                    per_period[to] = per_period.get(to, 0) + 1
                    if closed and len(per_period) and sics != ["all"] and (direction, to) not in seen:
                        seen[direction, to] = sics[0]
                    held += signed > z_needed(tests)
                    wrong += signed < -z_needed(tests)
    print(f"ranking on {'counts with dissolved' if closed else 'live-only counts'}: {named} named across "
          f"{len(SELECTIONS)} selections x 4 periods x 2 directions; {held} hold on exact counts with dissolved; "
          f"{wrong} clearly the other way; {total_tested} area tests run; named by period ending: {per_period}", flush=True)
    if closed:
        print("first division with a standout, per direction and period:", seen, flush=True)


def seasons() -> None:
    """Is the first quarter the busiest of each whole year? (the seasonal note in the server's answers)"""
    rows = raw.execute("""SELECT year, quarter, sum(companies) FROM (SELECT year, quarter, companies FROM grid
                          UNION ALL SELECT year, quarter, companies FROM grid_closed) WHERE year BETWEEN 2021 AND 2025
                          GROUP BY 1, 2 QUALIFY sum(companies) = max(sum(companies)) OVER (PARTITION BY year) ORDER BY 1""").fetchall()
    print("busiest quarter each year:", ", ".join(f"{y} Q{q_}" for y, q_, _ in rows), flush=True)


if __name__ == "__main__":
    run(False)
    run(True)
    seasons()
