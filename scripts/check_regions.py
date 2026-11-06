"""Batch A1 (regions, 3 Nov 2026): every region or nation's answer against exact counts.

Run: .venv/bin/python scripts/check_regions.py   (prints totals only, never a single small count)
For each of the 11 regions and nations and each 2-digit SIC division, latest year (2025-Q4 to 2026-Q3), still open
and including closed: does the server's likely range hold the exact count (formation-agent addresses left out, as the
server does), and is the region's own total (batch B: rounded on its own) within rounding of the sum of its council
areas' totals (each total off by at most 4 per rounded cell)? The same for every quarter row
(group_by quarter), every numbered council-area row inside the region (group_by area), and the region's one-year
survival range (default period, 2024-Q4 to 2025-Q3) against the exact survival rate.
"""
import sys
from pathlib import Path

import re

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import server  # noqa: E402

RANGE = re.compile(r"likely range ([\d,]+)–([\d,]+)")
raw = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
regions = server.db().execute("SELECT DISTINCT rgncd FROM regions ORDER BY 1").fetchall()
divisions = [r[0] for r in server.db().execute("SELECT DISTINCT left(code, 2) FROM sic ORDER BY 1").fetchall()]
LO, HI = 2025 * 4 + 4, 2026 * 4 + 3
S_LO, S_HI = 2024 * 4 + 4, 2025 * 4 + 3
SURV = re.compile(r"\(likely ([\d.]+)%–([\d.]+)%\) weren't dissolved")
tried = numbered = outside = not_sum = rows_checked = rows_outside = area_checked = area_outside = surv_checked = surv_outside = 0


def exact_in(tables: list[str], areas: list[str], d: str, lo: int, hi: int, extra: str = "") -> int:
    return sum(raw.execute(f"""SELECT coalesce(sum(companies), 0) FROM {t} WHERE NOT mass_postcode
        AND ladcd IN (SELECT unnest(?)) AND left(sic, 2) = ? AND year * 4 + quarter BETWEEN ? AND ? {extra}""",
                           [areas, d, lo, hi]).fetchone()[0] for t in tables)


for (rg,) in regions:
    areas = list(server.members(rg))
    for d in divisions:
        for closed in (False, True):
            r = server.count_incorporations_still_live([d], rg, "2025-Q4", "2026-Q3", "none", closed)
            by = server.count_incorporations_still_live([d], rg, "2025-Q4", "2026-Q3", "area", closed)
            tried += 1
            codes = server.expand_sics([d])[0]
            shown, cells = server.total_of(codes, LO, HI, rg, closed)
            parts = [server.total_of(codes, LO, HI, a, closed) for a in areas]
            not_sum += abs(shown - sum(v for v, _ in parts)) > 4 * (cells + sum(c for _, c in parts))
            tables = ["grid", "grid_closed"] if closed else ["grid"]
            exact = exact_in(tables, areas, d, LO, HI)
            got = RANGE.search(r.summary)  # the range the server actually gave
            if got:
                numbered += 1
                outside += not (int(got[1].replace(",", "")) <= exact <= int(got[2].replace(",", "")))
            assert by.rows, "area breakdown returned no rows"
            for row in by.rows:  # each council area inside the region
                if row["range"]:
                    e = exact_in(tables, [row["area_code"]], d, LO, HI)
                    area_checked += 1
                    area_outside += not (row["range"][0] <= e <= row["range"][1])
            qr = server.count_incorporations_still_live([d], rg, "2025-Q4", "2026-Q3", "quarter", closed)
            for row in qr.rows:
                if row["range"]:
                    k = int(row["quarter"][:4]) * 4 + int(row["quarter"][-1])
                    e = exact_in(tables, areas, d, k, k)
                    rows_checked += 1
                    rows_outside += not (row["range"][0] <= e <= row["range"][1])
        sv = server.one_year_survival([d], rg, None, None, 10)
        got = SURV.search(sv.summary)
        if got:
            early = exact_in(["grid_closed"], areas, d, S_LO, S_HI, "AND age = 'under_1y'")
            every = exact_in(["grid", "grid_closed"], areas, d, S_LO, S_HI)
            surv_checked += 1
            surv_outside += not (float(got[1]) <= 100 * (every - early) / every <= float(got[2]))
print(f"Region x division x open/closed answers: {tried:,}; numbered with a range: {numbered:,}; exact count outside "
      f"the range: {outside:,}; region further from the sum of its areas than rounding allows: {not_sum:,}. Region quarter rows with a range: "
      f"{rows_checked:,}; outside: {rows_outside:,}. One-council-area rows (the existing method): {area_checked:,}; "
      f"outside: {area_outside:,}. Region survival ranges: {surv_checked:,}; outside: "
      f"{surv_outside:,}.")
