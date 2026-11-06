"""Reproduce every number in MEMO.md from the server's released output only.

Run: .venv/bin/python scripts/memo_numbers.py
Share test: is Leeds's share of GB the same in both years? Log odds ratio of Leeds vs the rest of GB, with
Poisson variance plus the rounding variance of every protected cell summed (SPEC: 6.25 per cell). Batch B (3 Nov
2026): GB is its own rounded total, so the rest of GB carries GB's cells plus Leeds's (server.total_of gives the
cells, as the server counts them). |z| > 2 is a clear change, the same 2-sigma rule as release.change().
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import server  # noqa: E402
from release import share_z  # noqa: E402

DIGITAL = ["62011", "62012", "62020", "62090", "63110", "63120", "58290"]
LEEDS = "E08000035"
YEARS = [("2024-Q4", "2025-Q3"), ("2025-Q4", "2026-Q3")]
N_AREAS = server.db().execute("SELECT count(*) FROM areas WHERE NOT northern_ireland").fetchone()[0]


def num(text: str) -> int:
    return int(re.search(r"[\d,]+", text)[0].replace(",", ""))


def year(a: str, b: str) -> dict:
    leeds = server.count_incorporations_still_live(DIGITAL, LEEDS, a, b, "none", False)
    gb = server.count_incorporations_still_live(DIGITAL, "UK", a, b, "area", False)
    lo, hi = (int(q[:4]) * 4 + int(q[-1]) for q in (a, b))
    return {"leeds": num(leeds.summary), "leeds_mass": num(leeds.excluded.mass_postcode_companies),
            "range": re.search(r"likely range ([^)]*)", leeds.summary)[1],
            "gb": num(gb.summary), "gb_mass": num(gb.excluded.mass_postcode_companies),
            "cl": server.total_of(DIGITAL, lo, hi, LEEDS)[1], "cg": server.total_of(DIGITAL, lo, hi, "GB")[1]}


def z(a1: int, n1: int, a2: int, n2: int, cells_a, cells_n) -> float:
    return share_z(a1, n1, a2, n2, cells_a, cells_n)  # one implementation, shared with the server


if __name__ == "__main__":
    y1, y2 = (year(a, b) for a, b in YEARS)
    mass = len(DIGITAL) * 4  # agent cells: codes x quarters per area
    for (a, b), y in zip(YEARS, (y1, y2)):
        print(f"{a} to {b}: Leeds {y['leeds']:,} ({y['range']}), Leeds agent {y['leeds_mass']:,}, "
              f"GB {y['gb']:,}, GB agent {y['gb_mass']:,}")
    print(f"growth: Leeds {y2['leeds'] / y1['leeds'] - 1:+.0%}, GB {y2['gb'] / y1['gb'] - 1:+.0%}")
    out = z(y1["leeds"], y1["gb"], y2["leeds"], y2["gb"], (y1["cl"], y2["cl"]),
            (y1["cg"] + y1["cl"], y2["cg"] + y2["cl"]))
    print(f"agents left out: share {y1['leeds'] / y1['gb']:.2%} -> {y2['leeds'] / y2['gb']:.2%}, z = {out:.2f}")
    l1, l2 = y1["leeds"] + y1["leeds_mass"], y2["leeds"] + y2["leeds_mass"]
    g1, g2 = y1["gb"] + y1["gb_mass"], y2["gb"] + y2["gb_mass"]
    inc = z(l1, g1, l2, g2, (y1["cl"] + mass, y2["cl"] + mass),  # rest: GB + Leeds totals, every agent cell
            (y1["cg"] + y1["cl"] + mass * (N_AREAS + 1), y2["cg"] + y2["cl"] + mass * (N_AREAS + 1)))
    print(f"agents included: share {l1 / g1:.2%} -> {l2 / g2:.2%}, z = {inc:.2f}")
    out0 = z(y1["leeds"], y1["gb"], y2["leeds"], y2["gb"], 0, 0)
    inc0 = z(l1, g1, l2, g2, 0, 0)
    print(f"z without rounding noise (upper bound): left out {out0:.2f}, included {inc0:.2f}")
    print(f"GB agent-address growth: {y1['gb_mass']:,} -> {y2['gb_mass']:,}")
    # Survivorship, all industries (companies only, LLPs excluded), from the coverage table.
    rows = list(csv.DictReader(open(Path(__file__).resolve().parent.parent / "active/coverage/coverage.csv")))
    q = {r["quarter"]: r for r in rows if r["type"] == "companies"}
    def tot(qs, col): return sum(int(q[k][col]) for k in qs)
    old_q, new_q = ["2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3"], ["2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"]
    o1, o2, s1, s2 = tot(old_q, "official"), tot(new_q, "official"), tot(old_q, "snapshot"), tot(new_q, "snapshot")
    print(f"all industries: official {o1:,} -> {o2:,} ({o2 / o1 - 1:+.0%}); still open {s1:,} -> {s2:,} "
          f"({s2 / s1 - 1:+.0%}); coverage {s1 / o1:.0%} -> {s2 / o2:.0%}")
    surv = (s2 / s1) / (o2 / o1)  # how much survivorship alone inflates growth
    print(f"survivorship inflates growth by x{surv:.2f}; GB digital adjusted {(y2['gb'] / y1['gb']) / surv - 1:+.0%}, "
          f"Leeds digital adjusted {(y2['leeds'] / y1['leeds']) / surv - 1:+.0%} (if digital closes at the all-industry rate)")
