"""Testing phase: every area the rankings name as standing out, across industries and periods, checked on exact counts.

Run: .venv/bin/python scripts/check_standouts.py   -> active/testing/check-standouts.md (gitignored: exact counts)
A standout holds if the exact counts give the same direction past the same multiple-testing bar (exact z, no
rounding allowance). Found by the list-fix tests: Tower Hamlets food 2021 shown as 50 dissolved in a year, exactly 22.
"""
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import server  # noqa: E402
from release import odds_z, share_z, z_needed  # noqa: E402

raw = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
DIVISIONS = [c for c, in raw.execute("SELECT DISTINCT left(sic, 2) FROM grid WHERE sic <> 'none' ORDER BY 1").fetchall()]
OUT = ROOT / "active/testing/check-standouts.md"


def exact(sics, lo, hi, table, age=None) -> dict:
    like = " OR ".join("sic LIKE ?" for _ in sics)
    extra = f" AND age = '{age}'" if age else ""
    return {c: int(v) for c, v in raw.execute(
        f"SELECT ladcd, sum(companies) FROM {table} WHERE ({like}) AND NOT mass_postcode AND NOT northern_ireland "
        f"AND year * 4 + quarter BETWEEN ? AND ?{extra} GROUP BY ladcd", [s + "%" for s in sics] + [lo, hi]).fetchall()}


def with_dissolved(sics, lo, hi) -> dict:
    live, gone = exact(sics, lo, hi, "grid"), exact(sics, lo, hi, "grid_closed")
    return {k: live.get(k, 0) + gone.get(k, 0) for k in live.keys() | gone.keys()}


def q(s: str) -> int:
    return int(s[:4]) * 4 + int(s[-1])


def survival(lines: list[str]) -> tuple[int, int]:
    named = held = 0
    for d in DIVISIONS:
        for lo, hi in (("2021-Q1", "2021-Q4"), ("2022-Q1", "2022-Q4"), ("2023-Q1", "2023-Q4"), ("2024-Q4", "2025-Q3")):
            res = server.one_year_survival([d], "UK", lo, hi, 25)
            if not res.rows:
                continue
            tests = int(re.search(r"for all (\d+) areas", res.summary)[1])
            gone = exact([d], q(lo), q(hi), "grid_closed", "under_1y")
            allr = {k: v + exact([d], q(lo), q(hi), "grid").get(k, 0) for k, v in exact([d], q(lo), q(hi), "grid_closed").items()}
            allr.update({k: v for k, v in exact([d], q(lo), q(hi), "grid").items() if k not in allr})
            gc, ga = sum(gone.values()), sum(allr.values())
            for row in res.rows:
                e, n = gone.get(row["area_code"], 0), allr.get(row["area_code"], 0)
                ok = min(e, n - e) >= 10
                z = odds_z(gc - e, ga - gc - (n - e), e, n - e) if ok else 0.0
                lower = row["verdict"].startswith("lower")
                holds = ok and (z if lower else -z) > z_needed(tests)
                named, held = named + 1, held + holds
                lines.append(f"| survival | {d} | {lo}–{hi} | {row['area_name']} | {row['verdict'][:22]} | "
                             f"{row['dissolved_within_a_year']} of {row['registered']} | {e} of {n} | {z:.2f} | "
                             f"{z_needed(tests):.2f} | {'yes' if holds else '**NO**'} |")
    return named, held


def growth(lines: list[str]) -> tuple[int, int]:
    named = held = 0
    for d in DIVISIONS:
        for to in ("2026-Q3", "2025-Q3", "2024-Q3", "2023-Q3"):
            for direction in ("growing", "shrinking"):
                res = server.rank_areas_against_great_britain([d], direction, to, 25)
                if not res.rows:
                    continue
                tests = int(re.search(r"for all (\d+) areas", res.summary)[1])
                k2 = q(to)
                e1, e2 = with_dissolved([d], k2 - 7, k2 - 4), with_dissolved([d], k2 - 3, k2)
                g1, g2 = sum(e1.values()), sum(e2.values())
                for row in res.rows:
                    a, b = e1.get(row["area_code"], 0), e2.get(row["area_code"], 0)
                    z = share_z(a, g1, b, g2) if min(a, b) >= 10 else 0.0
                    holds = min(a, b) >= 10 and (z if direction == "growing" else -z) > z_needed(tests)
                    named, held = named + 1, held + holds
                    lines.append(f"| growth {direction} | {d} | to {to} | {row['area_name']} | {row['verdict'][:22]} | "
                                 f"{row['earlier']} → {row['latest']} | {a} → {b} | {z:.2f} | {z_needed(tests):.2f} | "
                                 f"{'yes' if holds else '**NO**'} |")
    return named, held


if __name__ == "__main__":
    lines = ["| Tool | SIC | Period | Area | Verdict | Shown | Exact | Exact z | Bar | Holds |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    sn, sh = survival(lines)
    gn, gh = growth(lines)
    head = [f"# Standouts checked on exact counts ({len(DIVISIONS)} SIC divisions)", "",
            f"Survival: {sh} of {sn} named areas hold. Growth: {gh} of {gn} hold.", ""]
    OUT.write_text("\n".join(head + lines) + "\n")
    print("\n".join(head + [l for l in lines if "**NO**" in l]))
