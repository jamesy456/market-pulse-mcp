"""Phase C benchmark truth: exact answers to both questions from the RAW grid (not the protected tables).

Run: .venv/bin/python scripts/truth_c.py   -> active/benchmark-c/truth.md
Cleaning = SIC group 812 (all 7 codes). GB council areas, formation-agent postcodes left out, unmatched postcodes
count in GB totals but are never ranked (same rules as the server). Tests use exact counts, so no rounding variance:
the log odds ratio z of an area against the rest of GB, with the Bonferroni bar for the number of areas tested.
Q1 is given twice: still open on 1 Nov 2026 (what Market Pulse ranks) and every company registered (open + dissolved).
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from release import odds_z, z_needed  # noqa: E402

CLEANING = "812%"
EARLIER, LATEST = (2024 * 4 + 4, 2025 * 4 + 3), (2025 * 4 + 4, 2026 * 4 + 3)  # year to 2025-Q3, year to 2026-Q3
COHORT = EARLIER  # one-year survival: every company in it has had a full year by 1 Nov 2026
con = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
GB = "NOT northern_ireland AND sic LIKE ? AND year * 4 + quarter BETWEEN ? AND ?"
AGENTS_OUT = True  # the main truth leaves formation-agent postcodes out; __main__ also prints them kept in


def per_area(table: str, period: tuple, extra: str = "") -> dict:
    where = GB + (" AND NOT mass_postcode" if AGENTS_OUT else "")
    rows = con.execute(f"SELECT ladcd, sum(companies) FROM {table} WHERE {where} {extra} GROUP BY ladcd",
                       [CLEANING, *period]).fetchall()
    return {code: int(n) for code, n in rows}


def add(*ds: dict) -> dict:
    return {k: sum(d.get(k, 0) for d in ds) for k in set().union(*ds)}


NAMES = dict(con.execute("SELECT DISTINCT ladcd, ladnm FROM grid WHERE NOT northern_ireland "
                         "AND ladcd <> 'unmatched'").fetchall())


def ranking(x1: dict, x2: dict) -> tuple[list, int]:
    """Share of GB in each period: (z, code, earlier, latest), strongest rise first, and how many were tested."""
    g1, g2 = sum(x1.values()), sum(x2.values())
    tested = [(c, x1.get(c, 0), x2.get(c, 0)) for c in NAMES]
    tested = [t for t in tested if min(t[1], t[2], g1 - t[1], g2 - t[2]) >= 10]
    return sorted(((odds_z(a, g1 - a, b, g2 - b), c, a, b) for c, a, b in tested), reverse=True), len(tested)


def q1(label: str, x1: dict, x2: dict) -> list[str]:
    g1, g2 = sum(x1.values()), sum(x2.values())
    ranked, n = ranking(x1, x2)
    need = z_needed(n)
    out = [f"### Q1, {label}", f"GB (formation agents {'out' if AGENTS_OUT else 'IN'}): {g1:,} -> {g2:,} ({g2 / g1 - 1:+.1%}). "
           f"{n} areas tested (at least 10 in both years); Bonferroni bar |z| > {need:.2f}.", "",
           "| Rank | Area | Earlier | Latest | Growth | Share earlier | Share latest | z | Clears bar |",
           "|---|---|---|---|---|---|---|---|---|"]
    for i, (z, c, a, b) in enumerate(ranked[:15], 1):
        out.append(f"| {i} | {NAMES[c]} | {a} | {b} | {b / a - 1:+.0%} | {a / g1:.2%} | {b / g2:.2%} | {z:.2f} | "
                   f"{'yes' if z > need else 'no'} |")
    shift = sorted(((x2.get(c, 0) / g2 - x1.get(c, 0) / g1, c) for c in NAMES), reverse=True)[:10]
    out += ["", "Top 10 by change in share of GB (percentage points): " + "; ".join(
        f"{NAMES[c]} {x1.get(c, 0) / g1:.2%} -> {x2.get(c, 0) / g2:.2%} ({d * 100:+.2f})" for d, c in shift)]
    pct = sorted(((x2.get(c, 0) / x1[c] - 1, c) for c in NAMES if x1.get(c, 0) >= 10), reverse=True)[:10]
    out += ["", "Top 10 by % growth (at least 10 in the earlier year): " + "; ".join(
        f"{NAMES[c]} {x1[c]} -> {x2.get(c, 0)} ({g:+.0%})" for g, c in pct)]
    top_abs = sorted(((x2.get(c, 0) - x1.get(c, 0), c) for c in NAMES), reverse=True)[:10]
    out += ["", "Top 10 by absolute increase: " + "; ".join(f"{NAMES[c]} {x1.get(c, 0)} -> {x2.get(c, 0)} (+{d})"
                                                         for d, c in top_abs)]
    # Biggest percentage growth among small areas: the "hotspots" a naive ranking would pick.
    small = sorted(((b / max(a, 1), c, a, b) for c in NAMES for a, b in [(x1.get(c, 0), x2.get(c, 0))]
                    if a < 10 and b >= 10), reverse=True)[:8]
    out += ["", "Too small to test (under 10 in the earlier year) but big jumps: "
            + "; ".join(f"{NAMES[c]} {a} -> {b}" for _, c, a, b in small), ""]
    return out


def q2() -> list[str]:
    early = per_area("grid_closed", COHORT, "AND age = 'under_1y'")
    rest = add(per_area("grid", COHORT), per_area("grid_closed", COHORT, "AND age = '1y_plus'"))
    gc, gs = sum(early.values()), sum(rest.values())
    tested = [(c, early.get(c, 0), rest.get(c, 0)) for c in NAMES]
    tested = [t for t in tested if min(t[1], t[2], gc - t[1], gs - t[2]) >= 10]
    need = z_needed(len(tested))
    ranked = sorted(((odds_z(gc - e, gs - s, e, s), c, e, s) for c, e, s in tested), reverse=True)
    out = ["### Q2, one-year survival, registered 2024-Q4 to 2025-Q3",
           f"GB (formation agents {'out' if AGENTS_OUT else 'IN'}): {gc + gs:,} registered, {gc:,} dissolved within a year, survival "
           f"{gs / (gc + gs):.1%}. {len(tested)} areas tested (at least 10 dissolved and 10 survived); "
           f"Bonferroni bar |z| > {need:.2f}. Positive z = lower survival.", "",
           "| Rank | Area | Registered | Dissolved < 1y | Survival | z | Clears bar |", "|---|---|---|---|---|---|---|"]
    for i, (z, c, e, s) in enumerate(ranked[:15], 1):
        out.append(f"| {i} | {NAMES[c]} | {e + s} | {e} | {s / (e + s):.1%} | {z:.2f} | {'yes' if z > need else 'no'} |")
    lowest = sorted(((s / (e + s), c, e, s) for c, e, s in [(c, early.get(c, 0), rest.get(c, 0)) for c in NAMES]
                     if e + s >= 10))[:8]
    out += ["", "Lowest raw survival among areas with 10+ registered (mostly too small to test): "
            + "; ".join(f"{NAMES[c]} {s / (e + s):.0%} of {e + s}" for _, c, e, s in lowest), ""]
    return out


def named_by_market_pulse() -> list[str]:
    """Areas Market Pulse's answers named (same in all 3 runs): exact counts against the protected ones it showed."""
    code = {n: c for c, n in NAMES.items()}

    def prot(table: str, c: str, period: tuple, age: str = "") -> int:
        return con.execute(f"SELECT coalesce(sum(protected), 0) FROM {table} WHERE ladcd = ? AND sic LIKE ? AND "
                           f"year * 4 + quarter BETWEEN ? AND ? {age}", [c, CLEANING, *period]).fetchone()[0]

    l1, l2 = per_area("grid", EARLIER), per_area("grid", LATEST)
    out = ["## Market Pulse's named areas: exact against protected", "",
           "| Q1 area (still open) | Exact earlier -> latest | Protected shown |", "|---|---|---|"]
    for n in ("Basildon", "Slough", "Hackney"):
        c = code[n]
        out.append(f"| {n} | {l1.get(c, 0)} -> {l2.get(c, 0)} | {prot('p_area', c, EARLIER)} -> {prot('p_area', c, LATEST)} |")
    early = per_area("grid_closed", COHORT, "AND age = 'under_1y'")
    rest = add(per_area("grid", COHORT), per_area("grid_closed", COHORT, "AND age = '1y_plus'"))
    out += ["", "| Q2 area | Exact dissolved < 1y / registered | Exact survival | Protected dissolved | Survival shown |",
            "|---|---|---|---|---|"]
    for n in ("Highland", "Aberdeen City", "Wigan", "Sunderland", "Islington"):
        c = code[n]
        e, s = early.get(c, 0), rest.get(c, 0)
        pe = prot("p_area_closed", c, COHORT, "AND age = 'under_1y'")
        ps = prot("p_area", c, COHORT) + prot("p_area_closed", c, COHORT, "AND age = '1y_plus'")
        out.append(f"| {n} | {e} / {e + s} | {s / (e + s):.0%} | {pe} | {ps / (pe + ps):.0%} |")
    prot_early = dict(con.execute("SELECT ladcd, sum(protected) FROM p_area_closed WHERE sic LIKE ? AND age = 'under_1y' "
                                  "AND year * 4 + quarter BETWEEN ? AND ? GROUP BY ladcd", [CLEANING, *COHORT]).fetchall())
    out += ["", f"Council areas with 10+ dissolved within a year: exact {sum(early.get(c, 0) >= 10 for c in NAMES)}, "
            f"protected {sum(prot_early.get(c, 0) >= 10 for c in NAMES)}.", ""]
    return out


def everything() -> list[str]:
    live1, live2 = per_area("grid", EARLIER), per_area("grid", LATEST)
    all1, all2 = (add(per_area("grid", p), per_area("grid_closed", p)) for p in (EARLIER, LATEST))
    return [*q1("still open on 1 Nov 2026", live1, live2), *q1("every company registered (open + dissolved)",
                                                                all1, all2), *q2()]


if __name__ == "__main__":
    lines = ["# Phase C truth (raw grid, exact counts)", "",
             "Cleaning = SIC 812xx (7 codes). Earlier = 2024-Q4 to 2025-Q3; latest = 2025-Q4 to 2026-Q3.",
             "Formation-agent postcodes are left out. Unmatched postcodes count in GB totals but can't be ranked. "
             "'Clears bar' is about the areas tested (enough companies), not every council.", "",
             "## Formation-agent postcodes left out (main truth)", "", *everything(), *named_by_market_pulse()]
    AGENTS_OUT = False
    lines += ["## Formation-agent postcodes kept in (for agents that don't exclude them)", "", *everything()]
    out = ROOT / "active/benchmark-c/truth.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
