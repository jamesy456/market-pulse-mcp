"""Testing phase: check the case-study scorer's findings about Market Pulse against exact counts.

Run: .venv/bin/python scripts/check_cases.py   -> active/testing/check-cases.md (gitignored: exact counts below 10)
1. C2: the area breakdown Market Pulse served (sorted on protected counts) against exact counts per area.
2. C4: Market Pulse's survival ranking against the exact ranking (truth_cases.py found two areas clearly lower).
3. The code sets the agents chose outside the rubric's acceptable sets: exact truth for those, so we can see
   whether the number was right for the codes stated.
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from mcp import Client  # noqa: E402

import server  # noqa: E402
from truth_cases import EARLIER, LATEST, n  # noqa: E402

OUT = ROOT / "active/testing/check-cases.md"


async def call(name: str, args: dict) -> dict:
    async with Client(server.mcp) as c:
        return (await c.call_tool(name, args)).structured_content


def c2(lines: list[str]) -> None:
    r = asyncio.run(call("count_incorporations_still_live", {"sic_codes": ["47260"], "area": "UK", "from_quarter": "2025-Q4",
                                                            "to_quarter": "2026-Q3", "group_by": "area", "include_closed": True}))
    exact = n(["47260"], LATEST, closed=True, by_area=True)
    shown = [row for row in r["rows"] if row["count"] is not None]
    lines += ["## C2: vape and tobacco (47260), every registered, by area, 2025-Q4 to 2026-Q3", "",
              f"Areas Market Pulse showed with a number: {len(shown)}. Areas with 10+ exactly: "
              f"{sum(v >= 10 for v in exact.values())}.", "", "| Area | Shown | Range shown | Exact |", "|---|---|---|---|"]
    lines += [f"| {row['area_name']} | {row['display']} | {row['range']} | {exact.get(row['area_code'], 0)} |" for row in shown]
    lines.append("")


def c4(lines: list[str]) -> None:
    r = asyncio.run(call("one_year_survival", {"sic_codes": ["41", "42", "43"], "area": "UK",
                                               "from_quarter": "2024-Q4", "to_quarter": "2025-Q3", "limit": 25}))
    lines += ["## C4: construction (41-43) one-year survival, 2024-Q4 to 2025-Q3", "", "Market Pulse summary: "
              + r["summary"], "", "Rows Market Pulse returned (first 25):", "", "```", json.dumps(r["rows"], indent=1)[:6000],
              "```", ""]
    names = {row.get("area_name") for row in r["rows"]}
    for a in ("North Yorkshire", "Stratford-on-Avon"):
        lines.append(f"- {a} in Market Pulse's rows: {a in names}")
    lines.append("")


def outside_sets(lines: list[str]) -> None:
    lines += ["## Code sets agents chose outside the rubric's sets: exact truth", "",
              "| Case | Codes | Definition | Exact |", "|---|---|---|---|"]
    for case, sics, period, area, closed in (
            ("C6", ["62011", "62012", "62020", "62090", "63110", "63120", "58290"], (2026 * 4 + 1, 2026 * 4 + 3),
             "Manchester", True),
            ("C6", ["62011", "62012", "62020", "62090", "63110", "63120", "58290"], (2026 * 4 + 1, 2026 * 4 + 3),
             "Manchester", None),
            ("C7", ["55201", "55209"], EARLIER, "Gwynedd", None), ("C7", ["55201", "55209"], LATEST, "Gwynedd", None),
            ("C7", ["55201", "55209"], EARLIER, "Gwynedd", True), ("C7", ["55201", "55209"], LATEST, "Gwynedd", True),
            ("C8", ["56101", "56102"], (2021 * 4 + 1, 2021 * 4 + 4), "Birmingham", True),
            ("C8 dissolved", ["56101", "56102"], (2021 * 4 + 1, 2021 * 4 + 4), "Birmingham", "only")):
        what = {None: "still open", True: "every registered", "only": "dissolved"}[closed]
        lines.append(f"| {case} | {'+'.join(sics)} | {what}, quarters {period} | {n(sics, period, area, closed)} |")
    lines.append("")


if __name__ == "__main__":
    out = ["# Check of the case scorer's findings (exact counts, local only)", ""]
    for step in (c2, c4, outside_sets):
        step(out)
    OUT.write_text("\n".join(out) + "\n")
    print("\n".join(out))
