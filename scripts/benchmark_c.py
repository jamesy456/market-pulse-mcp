"""Phase C benchmark: two market questions to fresh agents with an existing Companies House MCP or Market Pulse.

Run: .venv/bin/python scripts/benchmark_c.py [first] [last]   (default rounds 1-3)
     .venv/bin/python scripts/benchmark_c.py smoke              (one cheap call per MCP, checks both start)
Writes active/benchmark-c/<agent>-<question>-r<n>.json and metrics.md. Truth: scripts/truth_c.py. Scoring is by
reading each answer against the truth with the rubric in active/benchmark-c/RUBRIC.md.

An existing-MCP feasibility test, not a general claim. "ch" is an existing Companies House MCP (pinned,
installed outside this repo) with Bash/python3 and the ONS postcode lookup (the geography needs it). From its code,
one search returns at most ~1,000 results (offset <= 900) and needs a company-name fragment. Its wrapper reads
James's key from .env, so the key is never on a command line or in an agent's environment, and it is cut from the
raw output before anything is written. The ch runs go one at a time on the key's limit (600 requests per 5
minutes); Market Pulse runs alongside. Both agents get the same budget cap and the 30-minute timeout.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from benchmark import BENCH, FILES, MCP, ROOT, run

OUT = ROOT / "active/benchmark-c"
CH_DIR = BENCH / "ch-mcp"
CH = json.dumps({"mcpServers": {"companies-house": {"command": str(CH_DIR / "run.sh"), "args": []}}})
TODAY = " Today is 1 November 2026. Give the numbers and say how confident you are in them."
QUESTIONS = {  # neutral wording after the Codex design review: no Market Pulse concepts in the question
    "q1": ("Which council areas in Great Britain saw the strongest increase in newly incorporated cleaning companies "
           "in October 2025 to September 2026 versus the preceding year? Explain your geographic mapping, exclusions "
           "and uncertainty." + TODAY),
    "q2": ("Which council areas in Great Britain have the lowest one-year survival for cleaning companies "
           "incorporated from October 2024 to September 2025? Explain your definition of survival, the companies you "
           "included, your geographic mapping and your uncertainty." + TODAY),
}
LOOKUP = [f for f in FILES if "LU.csv" in f.name]
AGENTS = {
    "ch": {"budget": "4", "tools": "Bash,Read,Write", "mcp": CH, "allow": "mcp__companies-house", "files": LOOKUP,
           "extra": (" Use the companies-house tools. This folder holds the ONS postcode to local authority lookup "
                     f"({LOOKUP[0].name}). You can run python3 for analysis, in this folder only. "
                     "Don't use the internet except through those tools.")},
    "mcp": {"budget": "4", "tools": "", "mcp": MCP, "allow": "mcp__market-pulse",
            "extra": " Use the market-pulse tools."},
}


def key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("COMPANIES_HOUSE_API_KEY="):
            k = line.split("=", 1)[1].strip().strip("\"'")
            if len(k) >= 20:  # an empty or stub key would make the leak check meaningless
                return k
    raise SystemExit("COMPANIES_HOUSE_API_KEY missing or empty in .env")


def audited(agent: str, q: str, r: int, tag: str = "") -> dict:
    name = f"{agent}{tag}-{q}"
    res = run(agent, r, QUESTIONS[q], AGENTS, OUT, name, redact=key())  # redacted before it is written
    leaked = res["key_leaked"]
    res["touched_wrapper"] = str(CH_DIR) in json.dumps(res["tool_calls"]) or ".env" in json.dumps(res["tool_calls"])
    res["ch_calls"] = sum(c["tool"].startswith("mcp__companies-house") for c in res["tool_calls"])
    if leaked or res["touched_wrapper"]:
        print(f"AUDIT {name} r{r}: key_leaked={leaked} touched_wrapper={res['touched_wrapper']}", flush=True)
    return res


def row(name: str, r: int, res: dict) -> str:
    return (f"| {name} | {r} | {res.get('duration_ms', 0) / 1000:.0f}s | ${res.get('total_cost_usd', 0):.2f} | "
            f"{len(res['tool_calls'])} | {res.get('ch_calls', 0)} | {res.get('num_turns', '?')} | "
            f"{'yes' if res.get('result') else 'NO'} | {'LEAK' if res.get('key_leaked') else ''}"
            f"{' TOUCHED' if res.get('touched_wrapper') or res.get('touched_repo') else ''} |")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if sys.argv[1:] == ["smoke"]:
        smoke = {"q1": "Search Companies House for companies named 'tesco' and tell me how many results came back.",
                 "q2": "Use find_area to find the code for Leeds."}
        QUESTIONS.update(smoke)
        AGENTS["ch"]["budget"] = AGENTS["mcp"]["budget"] = "0.3"
        for agent, q in (("ch", "q1"), ("mcp", "q2")):
            res = audited(agent, q, 0)
            print(res.get("result", "")[:300])
        return
    if sys.argv[1:] == ["rerun-mcp"]:  # after the phase C fix: Market Pulse only, saved as mcp2-*, originals kept
        for r in (1, 2, 3):
            for q in QUESTIONS:
                print(row(f"mcp2-{q}", r, audited("mcp", q, r, "2")), flush=True)
        return
    first, last = (int(x) for x in sys.argv[1:3]) if len(sys.argv) > 2 else (1, 3)
    jobs = {a: [(q, r) for r in range(first, last + 1) for q in QUESTIONS] for a in AGENTS}
    with ThreadPoolExecutor(len(AGENTS)) as pool:  # one thread per agent: ch runs stay sequential on the shared key
        done = dict(zip(AGENTS, pool.map(lambda a: [(q, r, audited(a, q, r)) for q, r in jobs[a]], AGENTS)))
    rows = ["| Agent-question | Round | Time | Cost (API price) | Tool calls | CH tool calls | Turns | Answered | Audit |",
            "|---|---|---|---|---|---|---|---|---|"]
    rows += [row(f"{a}-{q}", r, res) for a, runs in done.items() for q, r, res in runs]
    (OUT / "metrics.md").write_text("# Phase C metrics\n\n" + "\n\n".join(f"**{k}:** {v}" for k, v in QUESTIONS.items())
                                    + "\n\n" + "\n".join(rows) + "\n")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
