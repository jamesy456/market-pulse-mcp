"""Open since 3 Nov (DECISIONS, batch A): area survival answers leave formation-agent addresses out. Does that flip a verdict?

Run: .venv/bin/python -u scripts/check_survival_agents.py   (prints totals only, never a single small count)
Exact counts, Great Britain. Every whole cohort that has had a full year: 2021, 2022, 2023, 2024 by calendar year and
the latest four such quarters. All industries, every 2-digit division, every 5-digit code. Each council area with at
least 10 dissolved within a year and 10 not, agents left out, against the rest of Great Britain, once with agents left
out and once with them put back on both sides. Exact z, no rounding allowance, so one_year_survival's own gate and test
are stricter and can pick different areas, and regions, custom periods and bundles aren't covered. The tests overlap:
the same companies sit in a code, its division and all industries, and in a calendar year and the latest cohort.
"""
import sys
from collections import Counter
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from release import odds_z, z_needed  # noqa: E402

g = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
LAST = 2025 * 4 + 3
COHORTS = [("2021", 2021 * 4 + 1, 2021 * 4 + 4), ("2022", 2022 * 4 + 1, 2022 * 4 + 4), ("2023", 2023 * 4 + 1, 2023 * 4 + 4),
           ("2024", 2024 * 4 + 1, 2024 * 4 + 4), ("latest", LAST - 3, LAST)]
AREAS = g.execute("SELECT count(DISTINCT ladcd) FROM areas WHERE NOT northern_ireland AND ladcd <> 'unmatched'").fetchone()[0]
g.execute("""CREATE TEMP TABLE base AS
    SELECT sic, ladcd, year * 4 + quarter AS k, mass_postcode AS agent, FALSE AS early, companies AS n
    FROM grid WHERE NOT northern_ireland
    UNION ALL SELECT sic, ladcd, year * 4 + quarter, mass_postcode, age = 'under_1y', companies
    FROM grid_closed WHERE NOT northern_ireland""")
g.execute("CREATE TEMP TABLE cohort (name VARCHAR, lo INT, hi INT)")
g.executemany("INSERT INTO cohort VALUES (?, ?, ?)", COHORTS)
LEVELS = {"all industries": "'all'", "division": "left(sic, 2)", "5-digit code": "sic"}


def rows(key: str, wanted: str) -> list:
    return g.execute(f"""
        WITH c AS (SELECT {key} AS key, ladcd, name,
                          coalesce(sum(n) FILTER (WHERE early AND NOT agent), 0) AS e_out,
                          coalesce(sum(n) FILTER (WHERE NOT early AND NOT agent), 0) AS s_out,
                          coalesce(sum(n) FILTER (WHERE early), 0) AS e_in, coalesce(sum(n) FILTER (WHERE NOT early), 0) AS s_in
                   FROM base JOIN cohort ON k BETWEEN lo AND hi WHERE {wanted} GROUP BY ALL),
             t AS (SELECT key, name, sum(e_out) AS ge_out, sum(s_out) AS gs_out, sum(e_in) AS ge_in, sum(s_in) AS gs_in
                   FROM c GROUP BY ALL)
        SELECT e_out::INT, s_out::INT, e_in::INT, s_in::INT, ge_out::INT, gs_out::INT, ge_in::INT, gs_in::INT, ladcd LIKE 'E09%'
        FROM c JOIN t USING (key, name) WHERE ladcd <> 'unmatched' AND e_out >= 10 AND s_out >= 10
          AND ge_out - e_out >= 10 AND gs_out - s_out >= 10""").fetchall()


def verdict(z: float, bar: float) -> int:
    return 1 if z > bar else -1 if z < -bar else 0


overall = Counter()


def report(name: str, data: list, bar: float, label: str) -> None:
    for group, picked in (("agents under 20% of GB", [r for r in data if 1 - (r[4] + r[5]) / (r[6] + r[7]) < 0.2]),
                          ("agents 20% or more", [r for r in data if 1 - (r[4] + r[5]) / (r[6] + r[7]) >= 0.2]),
                          ("London boroughs", [r for r in data if r[8]])):
        n = Counter()
        for e, s, ie, is_, ge, gs, ige, igs, _ in picked:
            out = verdict(odds_z(ge - e, gs - s, e, s), bar)
            back = verdict(odds_z(ige - ie, igs - is_, ie, is_), bar)
            n["tests"] += 1
            n["clear with agents out"] += out != 0
            n["kept"] += out != 0 and back == out
            n["gone"] += out != 0 and back == 0
            n["reversed"] += out != 0 and back == -out
            n["new with agents in"] += out == 0 and back != 0
        clear = n["clear with agents out"]
        if group != "London boroughs":  # London sits inside the other two groups
            overall[label, "clear"] += clear
            overall[label, "changed"] += n["gone"] + n["reversed"]
            overall[label, "reversed"] += n["reversed"]
        changed = (n["gone"] + n["reversed"]) / clear if clear else 0
        print(f"{name:>14} | {label:>6} | {group:>22} | {n['tests']:>7,} | {clear:>6,} | {n['kept']:>6,} | {n['gone']:>5,} | "
              f"{n['reversed']:>3,} | {n['new with agents in']:>5,} | {changed:>4.0%}", flush=True)


if __name__ == "__main__":
    print("level | bar | group | tests | clear with agents out | kept | gone | reversed | new with agents in | changed")
    for name, key in LEVELS.items():
        data = rows(key, "sic <> 'none'" if name != "all industries" else "TRUE")
        report(name, data, z_needed(1), "one")
        report(name, data, z_needed(AREAS), "list")
    for label, word in (("one", "single-area bar"), ("list", "list bar")):
        c, x, r = (overall[label, k] for k in ("clear", "changed", "reversed"))
        print(f"overall, {word}: {c:,} clear verdicts, {x:,} changed ({x / c:.0%}), {r:,} of them reversed", flush=True)
    print("GB rate of not being dissolved in the first year, agents out, then agents only:")
    for name, lo, hi in COHORTS:
        o, a = g.execute("""SELECT 1 - sum(n) FILTER (WHERE early AND NOT agent) * 1.0 / sum(n) FILTER (WHERE NOT agent),
                                   1 - sum(n) FILTER (WHERE early AND agent) * 1.0 / sum(n) FILTER (WHERE agent)
                            FROM base WHERE k BETWEEN ? AND ?""", [lo, hi]).fetchone()
        print(f"  {name}: {o:.1%}, {a:.1%}", flush=True)
