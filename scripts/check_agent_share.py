"""Testing phase (James's trial 2): leaving formation-agent addresses out can flip an area-vs-GB conclusion. London's
share of GB for SIC 62012/62090/63110/72190 fell with agents left out but rose with them in. This explores how often
that happens at each GB agent share, to pick a precautionary trigger for the warning (one pair of years, large codes).

Run: .venv/bin/python scripts/check_agent_share.py   (prints totals only, never a single small count)
Exact counts, still-open companies, Great Britain, latest four quarters (2025-Q4 to 2026-Q3) against the four before.
For each 5-digit SIC with 500+ GB companies in both years and each council area with 30+ companies (agents left out)
in both years: does the area's share of GB move the same way with agent addresses left out as with them in? A flip
counts only when the share moves by 5% or more of itself both ways, so near-zero wobbles don't count.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
g = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
LO2, HI2 = 2025 * 4 + 4, 2026 * 4 + 3
rows = g.execute("""
    WITH c AS (SELECT sic, ladcd, (year * 4 + quarter >= ?)::INT AS y,
                      sum(companies) FILTER (WHERE NOT mass_postcode) AS ex, sum(companies) AS inc
               FROM grid WHERE NOT northern_ireland AND length(sic) = 5 AND year * 4 + quarter BETWEEN ? AND ?
               GROUP BY ALL),
         gb AS (SELECT sic, y, sum(ex) AS gex, sum(inc) AS ginc FROM c GROUP BY ALL),
         ok AS (SELECT sic FROM gb GROUP BY sic HAVING count(*) = 2 AND min(gex) >= 500),
         share AS (SELECT sic, 1 - gex / ginc AS agents FROM gb WHERE y = 1 AND sic IN (SELECT sic FROM ok)),
         a AS (SELECT c.sic, ladcd,
                      max(ex / gex) FILTER (WHERE c.y = 1) / max(ex / gex) FILTER (WHERE c.y = 0) - 1 AS d_ex,
                      max(inc / ginc) FILTER (WHERE c.y = 1) / max(inc / ginc) FILTER (WHERE c.y = 0) - 1 AS d_in
               FROM c JOIN gb USING (sic, y) WHERE c.sic IN (SELECT sic FROM ok) AND ladcd <> 'unmatched'
               GROUP BY ALL HAVING count(*) = 2 AND min(ex) >= 30)
    SELECT CASE WHEN agents < 0.1 THEN 'under 10%' WHEN agents < 0.2 THEN '10-20%' WHEN agents < 0.3 THEN '20-30%'
                WHEN agents < 0.4 THEN '30-40%' ELSE '40%+' END AS bucket,
           count(DISTINCT sic), count(*),
           count(*) FILTER (WHERE sign(d_ex) <> sign(d_in) AND least(abs(d_ex), abs(d_in)) >= 0.05),
           count(*) FILTER (WHERE ladcd LIKE 'E09%'), count(*) FILTER (WHERE ladcd LIKE 'E09%' AND sign(d_ex) <> sign(d_in) AND least(abs(d_ex), abs(d_in)) >= 0.05)
    FROM a JOIN share USING (sic) GROUP BY bucket ORDER BY min(agents)""", [LO2, LO2 - 4, HI2]).fetchall()
print("GB agent share | codes | area tests | direction flips | London tests | London flips")
for b, codes, n, f, ln, lf in rows:
    print(f"{b:>14} | {codes:>5} | {n:>10} | {f:>5} ({f / n:.0%}) | {ln:>12} | {lf:>4} ({lf / ln if ln else 0:.0%})")
mass_london = g.execute("""SELECT sum(companies) FILTER (WHERE ladcd LIKE 'E09%') / sum(companies) FROM grid
    WHERE mass_postcode AND NOT northern_ireland AND year * 4 + quarter BETWEEN ? AND ?""", [LO2, HI2]).fetchone()[0]
print(f"Agent-address companies in London, latest year, every code: {mass_london:.0%}")
