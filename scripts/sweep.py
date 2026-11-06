"""Consistency sweep (testing phase): every SIC code and every GB council area through every tool, no AI calls.

Run: .venv/bin/python scripts/sweep.py   -> active/testing/sweep.md
Checks on every answer: no INTERNAL or unexpected error; no number below 10 shown as a count; percentages in 0-100 and
inside their likely range; the answer holds the summary and the snapshot date; counts including closed companies are
never below live-only counts; a 3-digit group is within rounding of the sum of its codes (batch B: each total is
rounded on its own, up to 4 per cell); quarter rows add up to the total; size and time.
"""
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import server  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
SMALL = re.compile(rf"(?<![\d,.\-–])\b[0-9]\b(?![\d,.%])(?!\s+(?:{MONTHS}))(?:\W+\w+){{0,2}}?\W+(?:compan|dissolved)", re.I)
PCT = re.compile(r"(\d+(?:\.\d)?)% \(likely ([\d.]+)%–([\d.]+)%\)")
LEAD = re.compile(r"^(?:About ([\d,]+)|Under 10 \(rounded\))")
problems, errors, times, checked = [], Counter(), [], Counter()


def call(name, *args):
    t = time.perf_counter()
    try:
        res = getattr(server, name)(*args)
    except ToolError as e:
        code = str(e).split(":")[0]
        errors[code] += 1
        if code == "INTERNAL":
            problems.append(f"INTERNAL {name}{args}")
        return None
    except Exception as e:  # anything else escaping @coded is a bug
        problems.append(f"UNCAUGHT {name}{args}: {type(e).__name__}")
        return None
    times.append((time.perf_counter() - t, name))
    check(name, args, res)
    return res


def small_fields(x) -> list:
    """Every count-like field anywhere in the structured result: a bare number string, or an int `count`."""
    if isinstance(x, dict):
        # A division is a SIC code; likely_rank is a place in a list (largest lists), never a count.
        return [v for k, val in x.items() if k not in ("range", "division", "likely_rank") for v in
                ([val] if k == "count" and isinstance(val, int) and val < 10 else small_fields(val))]
    if isinstance(x, list):
        return [v for i in x for v in small_fields(i)]
    if isinstance(x, str) and re.fullmatch(r"\d[\d,]*", x) and int(x.replace(",", "")) < 10:
        return [x]
    return []


def check(name, args, res):
    text = res.model_dump_json()
    where = f"{name}{args}"
    checked["fields scanned for small counts"] += 1
    if small_fields(res.model_dump()):
        problems.append(f"small count in a field: {where}: {small_fields(res.model_dump())[:3]}")
    if SMALL.search(res.answer) or any(isinstance(r.get("count"), int) and r["count"] < 10 for r in res.rows):
        problems.append(f"small count shown: {where}: {(SMALL.search(res.answer) or [''])[0]}")
    if not res.answer.startswith(res.summary) or "1 November 2026" not in res.answer:
        problems.append(f"answer missing summary or date: {where}")
    checked["answers"] += 1
    for p, lo, hi in PCT.findall(text):
        checked["rates with a range"] += 1
        if not (0 <= float(lo) <= float(p) + 0.5 and float(p) - 0.5 <= float(hi) <= 100):
            problems.append(f"rate outside range: {where}: {p}% ({lo}–{hi})")
    if len(text) > 60_000:
        problems.append(f"large response {len(text):,} bytes: {where}")


def lead(res):
    m = res and LEAD.match(res.summary)
    return None if not m else (int(m[1].replace(",", "")) if m[1] else 0)


def main():
    assert SMALL.search("About 5 companies") and SMALL.search("7 of them dissolved") and not SMALL.search(
        "on 1 November 2026. Companies")  # the leak check can still fire
    assert small_fields({"division": "01", "earlier": "5", "later": "15"}) == ["5"]  # only the code is exempt
    t0 = time.time()
    con = server.db()
    codes = [r[0] for r in con.execute("SELECT DISTINCT code FROM sic ORDER BY code").fetchall()]
    areas = [r[0] for r in con.execute("SELECT ladcd FROM areas WHERE NOT northern_ireland AND ladcd <> 'unmatched' "
                                       "ORDER BY ladcd").fetchall()]
    q = ("2026-Q3", "2026-Q3")
    refusals = [  # (expected code, tool, args): each must refuse with that code, never answer or crash
        ("BAD_AREA", "count_incorporations_still_live", (["812"], "N09000003", *q, "none", False)),  # Belfast: NI
        ("BAD_AREA", "count_incorporations_still_live", (["812"], "unmatched", *q, "none", False)),
        ("BAD_AREA", "count_incorporations_still_live", (["812"], "E99999999", *q, "none", False)),
        ("BAD_AREA", "compare_area_with_great_britain", (["812"], "UK", None)),
        ("BAD_AREA", "one_year_survival", (["812"], "Leeds", None, None, 10)),
        ("OUT_OF_RANGE", "count_incorporations_still_live", (["812"], "UK", "2026-Q4", "2026-Q4", "none", False)),
        ("OUT_OF_RANGE", "count_incorporations_still_live", (["812"], "UK", "2020-Q4", "2021-Q1", "none", False)),
        ("BAD_QUARTER", "count_incorporations_still_live", (["812"], "UK", "2026-Q5", "2026-Q5", "none", False)),
        ("BAD_RANGE", "count_incorporations_still_live", (["812"], "UK", "2026-Q3", "2026-Q1", "none", False)),
        ("BAD_GROUP", "count_incorporations_still_live", (["812"], "E08000035", *q, "area", False)),
        ("BAD_SIC", "count_incorporations_still_live", (["12345"], "UK", *q, "none", False)),
        ("BAD_SIC", "count_incorporations_still_live", (["1"], "UK", *q, "none", False)),
        ("BAD_SIC", "count_incorporations_still_live", (["81%"], "UK", *q, "none", False)),
        ("OUT_OF_RANGE", "one_year_survival", (["812"], "UK", None, "2026-Q3", 10)),
        ("OUT_OF_RANGE", "rank_areas_against_great_britain", (["812"], "growing", "2022-Q1", 10)),
        ("BAD_AREA", "compare_two_areas", (["812"], "E08000003", "E12000002")),  # Manchester is in the North West
        ("OUT_OF_RANGE", "compare_two_areas", (["812"], "E08000003", "E08000035", "2022-Q2", "2021-Q3")),
        ("BAD_RANGE", "compare_area_with_great_britain", (["812"], "E08000003", "2024-Q1", "2024-Q3")),
        ("BAD_AREA", "breakdown_by_industry", ("Leeds",)),
        ("BAD_AREA", "breakdown_by_industry", ("N09000003",)),  # Belfast: NI
        ("OUT_OF_RANGE", "breakdown_by_industry", ("UK", "2021-Q4", "2021-Q1")),
        ("BAD_AREA", "count_companies_live_now", (["812"], "N09000003")),  # Belfast: NI
        ("BAD_SIC", "count_companies_live_now", (["12345"], "UK")),
        ("BAD_AREA", "largest_industries", ("N09000003",)),  # Belfast: NI
        ("BAD_SIC", "largest_areas", (["12345"],)),
        ("BAD_RANGE", "largest_areas", (["812"], "council", "2026-Q1", "2026-Q3")),
        ("BAD_AREA", "registrations_against_closures", (["812"], "N09000003")),  # Belfast: NI
        ("BAD_SIC", "registrations_against_closures", (["12345"],)),
        ("BAD_RANGE", "registrations_against_closures", (["812"], "UK", "2026-Q1", "2026-Q3")),
        ("OUT_OF_RANGE", "registrations_against_closures", (["812"], "UK", "2026-Q1", "2020-Q4")),
    ]

    def ordered(res) -> None:  # largest lists: count order, numbered rows, and each rank span the right way round.
        # Spans needn't rise row by row: a smaller count over more rounded cells has a wider range.
        if res is None:
            return
        checked["largest lists in order"] += 1
        counts = [r["count"] for r in res.rows]
        spans = [[int(x) for x in r["likely_rank"].split("–")] for r in res.rows]
        if counts != sorted(counts, reverse=True) or any(c is None or c < 10 for c in counts) \
                or any(s[0] > s[-1] for s in spans):
            problems.append(f"largest list out of order: {res.summary[:80]}")
    for want, name, args in refusals:
        before = errors[want]
        res = call(name, *args)
        checked["refusals"] += 1
        if res is not None or errors[want] == before:
            problems.append(f"expected {want}: {name}{args} -> {'answered' if res else 'other error'}")
    for c in codes:  # every code through every tool
        live = call("count_incorporations_still_live", [c], "UK", *q, "none", False)
        allr = call("count_incorporations_still_live", [c], "UK", *q, "none", True)
        checked["closed >= live"] += bool(lead(live))
        if lead(live) and lead(allr) is not None and lead(allr) < lead(live):
            problems.append(f"closed-inclusive below live: {c}: {lead(allr)} < {lead(live)}")
        call("compare_area_with_great_britain", [c], "E08000003", None)
        call("rank_areas_against_great_britain", [c], "growing", None, 25)
        call("one_year_survival", [c], "UK", None, None, 25)
        call("count_companies_live_now", [c], "UK")
        ordered(call("largest_areas", [c], "council", None, None, True, 25))
        call("registrations_against_closures", [c])
    for a in areas:  # every council through the area tools, small and large industries
        call("count_incorporations_still_live", ["812"], a, "2025-Q4", "2026-Q3", "quarter", True)
        call("count_incorporations_still_live", ["47260"], a, "2021-Q1", "2026-Q3", "none", True)  # mostly tiny
        call("compare_area_with_great_britain", ["56"], a, None)
        call("compare_area_with_great_britain", ["62012"], a, None)
        if a != "E08000035":  # head to head with Leeds, latest year and a chosen, earlier six quarters
            call("compare_two_areas", ["56"], a, "E08000035")
            call("compare_two_areas", ["41", "42", "43"], a, "E08000035", "2024-Q2", "2023-Q1", "previous", False)
        call("compare_area_with_great_britain", ["62012"], a, "2023-Q4", "2023-Q2", "year_before", False)
        call("breakdown_by_industry", a, None, None, "year_before", True)
        call("one_year_survival", ["47"], a, None, None, 10)
        call("one_year_survival", ["41", "42", "43"], a, None, None, 10)
        call("count_companies_live_now", ["812"], a)
        call("count_companies_live_now", ["all"], a)
        ordered(call("largest_industries", a, None, None, True, 25))
        call("registrations_against_closures", ["all"], a)
        call("registrations_against_closures", ["47260"], a, "2026-Q3", "2026-Q3")  # mostly tiny, under a year
    for g in sorted({c[:3] for c in codes if c.isdigit()}):  # a group is within rounding of the sum of its codes
        members = [c for c in codes if c.startswith(g)]
        parts = [lead(call("count_incorporations_still_live", [c], "UK", *q, "none", False)) for c in members]
        whole = lead(call("count_incorporations_still_live", [g], "UK", *q, "none", False))
        checked["group within rounding of its codes"] += bool(parts and all(p and p >= 10 for p in parts))
        if parts and all(p and p >= 10 for p in parts) and abs(whole - sum(parts)) > 4 * (len(members) + 1):
            problems.append(f"group {g} total {whole} is further from the sum of its codes {sum(parts)} than rounding allows")
    for d in sorted({c[:2] for c in codes if c.isdigit()}):  # quarter rows add up to the total
        res = call("count_incorporations_still_live", [d], "UK", "2021-Q1", "2026-Q3", "quarter", True)
        checked["quarter rows = total"] += bool(res and all(r["count"] for r in res.rows))
        if res and all(r["count"] for r in res.rows) and lead(res) != sum(r["count"] for r in res.rows):
            problems.append(f"division {d}: quarter rows {sum(r['count'] for r in res.rows)} != total {lead(res)}")
    for name, args in [("count_incorporations_still_live", (["01110"], "UK", "2021-Q1", "2026-Q3", "area", True)),
                       ("count_incorporations_still_live", (["none"], "UK", "2021-Q1", "2026-Q3", "quarter", False))]:
        call(name, *args)  # the biggest shapes
    times.sort(reverse=True)
    out = ["# Consistency sweep", "", f"{len(codes)} SIC codes and {len(areas)} GB council areas; "
           f"{len(times):,} answers in {time.time() - t0:.0f} s. Slowest: "
           + "; ".join(f"{n} {s:.2f} s" for s, n in times[:3]) + ".", "",
           f"Expected refusals (coded errors): {dict(errors) or 'none'}.", "",
           f"Checks that ran: {dict(checked)}.", "",
           f"**Problems: {len(problems)}**", *[f"- {p}" for p in problems[:200]], ""]
    (ROOT / "active/testing/sweep.md").write_text("\n".join(out))
    print("\n".join(out[:8]), *problems[:40], sep="\n")


if __name__ == "__main__":
    main()
