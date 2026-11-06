"""Testing phase: exact answers to the 8 case studies, from the RAW grid (not the protected tables).

Run: .venv/bin/python scripts/truth_cases.py   -> active/testing/truth-cases.md (gitignored: it holds exact counts
below 10). Each answer is given for both definitions an agent might use (still open on 1 Nov 2026, or every company
registered), with formation-agent postcodes left out (as Market Pulse does) and kept in (as a raw search would).
Earlier = Oct 2024-Sep 2025, latest = Oct 2025-Sep 2026. Change tests use exact counts (no rounding variance):
z = (b - a) / sqrt(a + b) for counts; the log odds ratio for shares and survival; Bonferroni bar for rankings.
"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from release import odds_z, z_needed  # noqa: E402

con = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
EARLIER, LATEST = (2024 * 4 + 4, 2025 * 4 + 3), (2025 * 4 + 4, 2026 * 4 + 3)
AREA = dict(con.execute("SELECT ladnm, ladcd FROM areas").fetchall())
NAME = {v: k for k, v in AREA.items()}
AGENTS_IN = False


def n(sics, period, area=None, closed=None, by_area=False, age=None) -> int | dict:
    """Exact count. closed: None = still open, True = every company registered (open + dissolved), "only" = dissolved."""
    where = ("(" + " OR ".join("sic LIKE ?" for _ in sics) + ") AND year * 4 + quarter BETWEEN ? AND ?"
             + ("" if AGENTS_IN else " AND NOT mass_postcode") + (" AND ladcd = ?" if area else " AND NOT northern_ireland"))
    params = [s + "%" for s in sics] + list(period) + ([AREA[area]] if area else [])
    tables = {None: ["grid"], True: ["grid", "grid_closed"], "only": ["grid_closed"]}[closed]
    out = {}
    for t in tables:
        extra = f" AND age = '{age}'" if age and t == "grid_closed" else ""
        sql = f"SELECT {'ladcd, ' if by_area else ''}sum(companies) FROM {t} WHERE {where}{extra}" + (" GROUP BY ladcd" if by_area else "")
        for *k, v in con.execute(sql, params).fetchall():
            out[tuple(k)] = out.get(tuple(k), 0) + int(v or 0)
    return {k[0]: v for k, v in out.items()} if by_area else sum(out.values())


def change(a: int, b: int) -> str:
    if min(a, b) < 10:
        return f"{a} -> {b}: too few to test (under 10)"
    z = (b - a) / (a + b) ** 0.5
    return f"{a} -> {b} ({b / a - 1:+.0%}), z = {z:.2f}: {'clear ' + ('rise' if z > 0 else 'fall') if abs(z) > 2 else 'no clear change'}"


def share(sics, area, closed) -> str:
    a1, a2 = n(sics, EARLIER, area, closed), n(sics, LATEST, area, closed)
    g1, g2 = n(sics, EARLIER, None, closed), n(sics, LATEST, None, closed)
    z = odds_z(a1, g1 - a1, a2, g2 - a2)
    return (f"{area} {change(a1, a2)}; GB {g1:,} -> {g2:,} ({g2 / g1 - 1:+.0%}); share {a1 / g1:.2%} -> {a2 / g2:.2%}, "
            f"z = {z:.2f}: {'clear ' + ('rise' if z > 0 else 'fall') + ' in share' if abs(z) > 2 else 'no clear change in share'}")


def cases() -> list[str]:
    out = []
    for closed, label in ((None, "still open on 1 Nov 2026"), (True, "every company registered")):
        out += [f"### {label}, formation agents {'IN' if AGENTS_IN else 'out'}", ""]
        out.append(f"- **C1 Cardiff cafes and takeaways (56102, 56103):** {share(['56102', '56103'], 'Cardiff', closed)}")
        out.append(f"  - C1 with all of 561 (56101-56103): {share(['561'], 'Cardiff', closed)}")
        g = n(["47260"], LATEST, None, closed, by_area=True)
        top = sorted(((v, NAME.get(k, k)) for k, v in g.items() if k != "unmatched"), reverse=True)[:5]
        out.append(f"- **C2 vape and tobacco shops (47260), GB:** {change(n(['47260'], EARLIER, None, closed), n(['47260'], LATEST, None, closed))}. "
                   f"Top 5 areas, latest year: " + "; ".join(f"{a} {v}" for v, a in top)
                   + f". Areas with 10+ in the latest year: {sum(v >= 10 for k, v in g.items() if k != 'unmatched')}")
        out.append(f"- **C3 Glasgow hair and beauty (96020):** {change(n(['96020'], EARLIER, 'Glasgow City', closed), n(['96020'], LATEST, 'Glasgow City', closed))}")
        ny = lambda s: change(n(s, EARLIER, 'North Yorkshire', closed), n(s, LATEST, 'North Yorkshire', closed))
        out.append(f"- **C5 North Yorkshire software:** 62012 {ny(['62012'])}; 62011+62012 {ny(['62011', '62012'])}; "
                   f"62012+62020 {ny(['62012', '62020'])}; all of 62 {ny(['62'])}")
        m = ", ".join(f"{s} {n([s], (2026 * 4 + 1, 2026 * 4 + 3), 'Manchester', closed)}" for s in ("62012", "62020", "62090", "63110", "72190"))
        out.append(f"- **C6 Manchester 'AI companies', 2026-Q1 to Q3 (no AI code exists; candidate proxies):** {m}")
        gw = lambda s: change(n(s, EARLIER, 'Gwynedd', closed), n(s, LATEST, 'Gwynedd', closed))
        out.append(f"- **C7 Gwynedd holiday lets:** 55209 {gw(['55209'])}; all of 552 (55201, 55202, 55209) {gw(['552'])}; "
                   f"55209+68209 {gw(['55209', '68209'])}; 552+68209 {gw(['552', '68209'])}")
        out.append("")
    # C4: one-year survival, construction (41, 42, 43), cohort = EARLIER (all have had a full year by 1 Nov 2026)
    con_sics = ["41", "42", "43"]
    early = n(con_sics, EARLIER, None, "only", by_area=True, age="under_1y")
    live, later = n(con_sics, EARLIER, None, None, by_area=True), n(con_sics, EARLIER, None, "only", by_area=True, age="1y_plus")
    rest = {k: live.get(k, 0) + later.get(k, 0) for k in set(early) | set(live) | set(later)}  # Codex: union of all three
    ge, gs = sum(early.values()), sum(rest.values())
    tested = [(k, early.get(k, 0), rest[k]) for k in rest if k != "unmatched" and min(early.get(k, 0), rest[k], ge - early.get(k, 0), gs - rest[k]) >= 10]
    need = z_needed(len(tested))
    ranked = sorted(((odds_z(ge - e, gs - s, e, s), k, e, s) for k, e, s in tested), reverse=True)
    lowest_raw = sorted((s / (e + s), NAME.get(k, k)) for k, e, s in [(k, early.get(k, 0), rest[k]) for k in rest]
                        if k != "unmatched" and e + s >= 20)[:5]
    out += [f"- **C4 construction (41-43) one-year survival, cohort Oct 2024-Sep 2025:** GB {gs / (ge + gs):.1%} "
            f"({ge:,} dissolved within a year of {ge + gs:,}). {len(tested)} areas tested, bar |z| > {need:.2f}. "
            f"Clearly lower: {[NAME[k] for z, k, e, s in ranked if z > need] or 'none'}. Lowest 5 tested: "
            + "; ".join(f"{NAME[k]} {s / (e + s):.1%} (z {z:.2f})" for z, k, e, s in ranked[:5])
            + ". Lowest raw rates, areas with 20+ registered (mostly too small to test): "
            + "; ".join(f"{a} {p:.0%}" for p, a in lowest_raw), ""]
    # C8: Birmingham restaurants incorporated in 2021: how many dissolved since
    for s in (["56101"], ["561"]):
        live, gone = n(s, (2021 * 4 + 1, 2021 * 4 + 4), "Birmingham"), n(s, (2021 * 4 + 1, 2021 * 4 + 4), "Birmingham", "only")
        out.append(f"- **C8 Birmingham restaurants ({'+'.join(s)}) incorporated in 2021:** {live + gone} registered, {gone} "
                   f"dissolved by 1 Nov 2026 ({gone / (live + gone):.0%}), {live} still open")
    out.append("")
    return out


if __name__ == "__main__":
    lines = ["# Case-study truth (raw grid, exact counts; local only, never published)", ""]
    lines += ["## Formation-agent postcodes left out (Market Pulse's rule)", "", *cases()]
    AGENTS_IN = True
    lines += ["## Formation-agent postcodes kept in (a raw search's rule)", "", *cases()]
    (ROOT / "active/testing/truth-cases.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
