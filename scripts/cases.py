"""Testing phase: 8 case studies to fresh agents: Market Pulse, web search and three existing Companies House MCPs.

Run: .venv/bin/python scripts/cases.py mine     (Market Pulse and web, side by side; Claude can run this)
     .venv/bin/python scripts/cases.py mcp      (Market Pulse alone, after a server change; move the old mcp runs aside first)
     .venv/bin/python scripts/cases.py ch       (an existing Companies House MCP; James runs it, it uses his key)
     .venv/bin/python scripts/cases.py mcp_b    (a second existing MCP; James runs it, his key)
     .venv/bin/python scripts/cases.py mcp_c    (a third, on the bulk file; no key, Claude can run it)
     .venv/bin/python scripts/cases.py metrics  (rebuild metrics.md from the saved runs)
Writes active/testing/cases/<agent>-c<n>-r<round>.json and metrics.md. Design and scoring: active/testing/CASES.md;
truth: scripts/truth_cases.py. 3 rounds per agent.
"""
import json
import sys
from statistics import median
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from benchmark import AGENTS as FIRST, ROOT, run
from benchmark_c import AGENTS as PHASE_C, LOOKUP, audited, key

OUT = ROOT / "active/testing/cases"
ROUNDS = (1, 2, 3)
TODAY = " Today is 1 November 2026. Give the numbers and say how confident you are in them."
CASES = {
    "c1": "Are new cafés, coffee shops and takeaway businesses being set up faster in Cardiff than in the rest of Great "
          "Britain? Compare October 2025 to September 2026 with the year before.",
    "c2": "Which council areas in Great Britain have had the most new vape and tobacco shop companies in the last year "
          "(October 2025 to September 2026), and has the number of new ones across Great Britain gone up or down "
          "compared with the year before?",
    "c3": "How many new hairdressing and beauty businesses were registered as companies in Glasgow in the year to "
          "September 2026, and is that more than the year before?",
    "c4": "What share of construction companies incorporated in Great Britain between October 2024 and September 2025 "
          "were still going a year later, and which council areas did worst?",
    "c5": "How many new software development companies started in North Yorkshire in October 2025 to September 2026, "
          "compared with the year before?",
    "c6": "How many AI companies were started in Manchester in 2026 so far?",
    "c7": "Are more holiday-let businesses being set up in Gwynedd than a year ago?",
    "c8": "Of the restaurant companies incorporated in Birmingham in 2021, how many have since been dissolved?",
}
AGENTS = {"mcp": PHASE_C["mcp"], "web": FIRST["web"], "ch": PHASE_C["ch"]}
# Two more existing MCPs, on James's go-ahead after the first scoring. Code read before running, pinned, installed
# outside this repo. Same set-up as "ch": Python and the ONS postcode lookup, no internet beyond the tools.
RIVALS = ROOT.parent / "market-pulse-bench/rivals"
SETUP = (" This folder holds the ONS postcode to local authority lookup ({}). You can run python3 for analysis, in "
         "this folder only. Don't use the internet except through those tools.")
AGENTS["mcp_b"] = {  # pinned to one commit: live API with advanced search
    "budget": "4", "tools": "Bash,Read,Write", "allow": "mcp__ch-search", "files": LOOKUP,
    "mcp": json.dumps({"mcpServers": {"ch-search": {"command": str(RIVALS / "mcp-b-run.sh"), "args": []}}}),
    "extra": " Use the ch-search tools." + SETUP.format(LOOKUP[0].name)}
AGENTS["mcp_c"] = {  # pinned to one commit: the 1 Nov 2026 bulk file in SQLite (live companies)
    "budget": "4", "tools": "Bash,Read,Write", "allow": "mcp__companies", "files": LOOKUP,
    "mcp": json.dumps({"mcpServers": {"companies": {"command": str(RIVALS / "mcp-c-venv/bin/python"),
                                                     "args": [str(RIVALS / "mcp-c/mcp_server.py")]}}}),
    "extra": " Use the companies tools." + SETUP.format(LOOKUP[0].name)}


def one(agent: str, c: str, r: int) -> dict:
    if agent == "ch":  # the key wrapper's audit: redacts the key and flags any leak or touch of the wrapper
        import benchmark_c
        benchmark_c.QUESTIONS[c] = CASES[c] + TODAY
        res = audited("ch", c, r)  # it saves under benchmark-c before adding its audit flags, so save again here
        (ROOT / f"active/benchmark-c/ch-{c}-r{r}.json").unlink()
        (OUT / f"ch-{c}-r{r}.json").write_text(json.dumps(res, indent=2))
        return res
    res = run(agent, r, CASES[c] + TODAY, AGENTS, OUT, f"{agent}-{c}", redact=key() if agent == "mcp_b" else "")
    if agent in ("mcp_b", "mcp_c"):  # audit: no reading the wrapper, the key file or the rival's database directly
        calls = json.dumps(res["tool_calls"]).replace("os.environ", "")  # Python's name, not a read of the .env file
        res["touched_wrapper"] = str(RIVALS) in calls or ".env" in calls or "companies.db" in calls
        (OUT / f"{agent}-{c}-r{r}.json").write_text(json.dumps(res, indent=2))
    return res


def metrics() -> None:
    rows = ["| Agent | Case | Round | Time | Cost (API price) | Tool calls | Answered | Audit |", "|---|---|---|---|---|---|---|---|"]
    for f in sorted(OUT.glob("*-c*-r*.json")):
        res = json.loads(f.read_text())
        agent, c, r = f.stem.split("-")
        rows.append(f"| {agent} | {c} | {r[1:]} | {res.get('duration_ms', 0) / 1000:.0f}s | ${res.get('total_cost_usd', 0):.2f} "
                    f"| {len(res.get('tool_calls', []))} | {'yes' if res.get('result') else 'NO'} | "
                    f"{'LEAK ' if res.get('key_leaked') else ''}{'TOUCHED' if res.get('touched_repo') or res.get('touched_wrapper') else ''} |")
    per = {}
    for f in sorted(OUT.glob("*-c*-r*.json")):
        per.setdefault(f.stem.split("-")[0], []).append(json.loads(f.read_text()))
    med = ["| Agent | Runs | Answered | Median time | Median cost | Median tool calls | Audit flags |",
           "|---|---|---|---|---|---|---|"]
    for agent, rs in per.items():
        med.append(f"| {agent} | {len(rs)} | {sum(bool(r.get('result')) for r in rs)} | "
                   f"{median(r.get('duration_ms', 0) for r in rs) / 1000:.0f}s | ${median(r.get('total_cost_usd', 0) for r in rs):.2f} | "
                   f"{median(len(r.get('tool_calls', [])) for r in rs):g} | "
                   f"{sum(bool(r.get('key_leaked') or r.get('touched_repo') or r.get('touched_wrapper')) for r in rs)} |")
    (OUT / "metrics.md").write_text("# Case-study metrics\n\n" + "\n".join(f"**{c}:** {q}" for c, q in CASES.items())
                                    + "\n\n" + "\n".join(med) + "\n\n" + "\n".join(rows) + "\n")
    print("\n".join(med))
    print("\n".join(rows))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode in ("mine", "mcp"):  # mcp alone: rerun Market Pulse after a server change (testing phase: list fix)
        jobs = {a: [(c, r) for r in ROUNDS for c in CASES] for a in (("mcp", "web") if mode == "mine" else ("mcp",))}
        with ThreadPoolExecutor(2) as pool:  # one thread per agent; runs within an agent go one at a time
            list(pool.map(lambda a: [one(a, c, r) for c, r in jobs[a]], jobs))
    elif mode in ("ch", "mcp_b", "mcp_c"):  # one at a time: the two API MCPs share the key's rate limit
        if mode != "mcp_c":
            key()  # fail fast if the key is missing
        for r in ROUNDS:
            for c in CASES:
                one(mode, c, r)
    elif mode != "metrics":
        raise SystemExit(__doc__)
    metrics()


if __name__ == "__main__":
    main()
