"""Testing phase: how often a four-quarter count shown under 10 is really 10 or more (case C7: Gwynedd 55209,
shown as "fewer than 10" for a true 13; since 2 Nov 2026 the label is "under 10 (rounded)" with a note).

Run: .venv/bin/python scripts/check_fewer_than_10.py   (prints totals only, never a single small count)
Every 5-digit SIC x GB council area, latest year (2025-Q4 to 2026-Q3), still-open companies, formation-agent
postcodes out: the protected sum the server shows against the exact sum. Each quarter's true value can be up to 4
above its rounded cell, so a shown sum under 10 over four quarters can hide a true 10 or more.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "data/serve.duckdb"), read_only=True)
con.execute(f"ATTACH '{ROOT / 'data/grid.duckdb'}' AS raw (READ_ONLY)")
LO, HI = 2025 * 4 + 4, 2026 * 4 + 3
shown_under, really_10_plus = con.execute("""
    WITH p AS (SELECT ladcd, sic, sum(protected) AS shown FROM p_area
               WHERE year * 4 + quarter BETWEEN ? AND ? AND ladcd <> 'unmatched' GROUP BY ALL),
         e AS (SELECT ladcd, sic, sum(companies) AS exact FROM raw.grid
               WHERE year * 4 + quarter BETWEEN ? AND ? AND NOT mass_postcode AND NOT northern_ireland
               AND ladcd <> 'unmatched' AND length(sic) = 5 GROUP BY ALL)
    SELECT count(*) FILTER (WHERE coalesce(p.shown, 0) < 10),
           count(*) FILTER (WHERE coalesce(p.shown, 0) < 10 AND e.exact >= 10)
    FROM e LEFT JOIN p USING (ladcd, sic) WHERE e.exact > 0""", [LO, HI, LO, HI]).fetchone()
print(f"Code x area pairs with any company in the latest year and shown under 10: {shown_under:,}; "
      f"really 10 or more: {really_10_plus:,} ({really_10_plus / shown_under:.2%}).")
