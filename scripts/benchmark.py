"""Benchmark: the same question to three fresh agents (web only, raw data, Market Pulse), timed and costed.

Run: .venv/bin/python scripts/benchmark.py [first] [last]   (default rounds 1-3; the three agents run side by side)
Writes active/benchmark/<agent>-r<n>.json (answer, metrics, every tool call) and active/benchmark/metrics.md.
Correctness and caveats are scored by reading each answer against the raw grid (see DECISIONS.md).

The raw-data agent works in a fresh folder outside this repo per run, holding hard links to the two public files
(snapshot CSV, ONS postcode lookup) and a Python with DuckDB, so earlier runs and this repo can't help it.
"""
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "active/benchmark"
BENCH = ROOT.parent / "market-pulse-bench"  # next to the repo, outside it on purpose
MODEL = "claude-sonnet-5-5"
FILES = [ROOT / "data/snapshots/BasicCompanyDataAsOneFile-2026-11-01.csv",
         ROOT / "data/lookup/PCD_OA21_LSOA21_MSOA21_LAD_AUG26_UK_LU.csv"]

QUESTION = ("How many new cleaning companies started in Leeds in 2026 Q3, and is that up on the same quarter last "
            "year? Today is 1 November 2026. Give the numbers and say how confident you are in them.")
MCP = json.dumps({"mcpServers": {"market-pulse": {
    "command": str(ROOT / ".venv/bin/python"), "args": [str(ROOT / "src/server.py")]}}})

AGENTS = {
    "web": {"budget": "2", "tools": "WebSearch,WebFetch", "extra": (
        " Research it on the web. Before fetching any site, read its robots.txt and obey it, including "
        "Crawl-delay. If a site blocks or challenges you, use search snippets instead.")},
    "raw": {"budget": "4", "tools": "Bash,Read,Glob,Grep,Write", "extra": (
        " This folder holds the Companies House Free Company Data Product snapshot of 1 November 2026 "
        "(BasicCompanyDataAsOneFile-2026-11-01.csv) and the ONS postcode to local authority lookup "
        "(PCD_OA21_LSOA21_MSOA21_LAD_AUG26_UK_LU.csv). Python with DuckDB is at ../env/bin/python. "
        "Work only with the files in this folder and don't use the internet."), "files": FILES},
    "mcp":{"budget": "1", "tools": "", "extra": " Use the market-pulse tools.", "mcp": MCP, "allow": "mcp__market-pulse"},
}


def workdir(name: str, r: int, files=()) -> Path:
    d = BENCH / f"{name}-r{r}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    for f in files:
        os.link(f, d / f.name)  # hard link: no copy, no path back to the repo
    return d


def run(agent: str, r: int, question: str = QUESTION, agents: dict = AGENTS, out: Path = OUT, name: str = "",
        redact: str = "") -> dict:
    """Phase C reuses this with its own questions and agents; the defaults are the first benchmark, unchanged.
    `redact` (a secret) is cut from the raw output before anything is parsed or written."""
    # Accepted risk, AUDIT-FINDINGS.md: register text could steer an agent with a shell to read .env or raw data.
    if "Bash" in agents[agent]["tools"]:
        raise SystemExit(f"Refused: agent {agent!r} would have shell access while reading register text")
    a, cwd = agents[agent], workdir(name or agent, r, agents[agent].get("files", ()))
    cmd = ["claude", "-p", question + a["extra"], "--model", MODEL, "--output-format", "stream-json", "--verbose",
           "--tools", a["tools"], "--setting-sources", "", "--no-session-persistence", "--max-budget-usd", a["budget"],
           "--strict-mcp-config"]
    if a.get("mcp"):
        cmd += ["--mcp-config", a["mcp"], "--allowedTools", ",".join(t for t in (a["allow"], a["tools"]) if t)]
    else:
        cmd += ["--allowedTools", a["tools"]]
    try:
        env = {k: v for k, v in os.environ.items() if k != "COMPANIES_HOUSE_API_KEY"}  # agents never inherit the key
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=cwd, stdin=subprocess.DEVNULL,
                              env=env)
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        stdout, stderr = ((x.decode() if isinstance(x, bytes) else (x or "")) for x in (e.stdout, e.stderr))
    leaked = bool(redact) and (redact in stdout or redact in stderr)  # stderr is checked, never written
    if leaked:
        stdout = stdout.replace(redact, "[REDACTED-KEY]")
    res, calls, results = {"result": "", "error": "timeout or no result line"}, [], []
    for line in stdout.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") == "result":
            res = d
        if d.get("type") == "assistant":
            calls += [{"tool": c["name"], "input": c["input"]} for c in d["message"]["content"] if c.get("type") == "tool_use"]
        if d.get("type") == "user":  # testing phase: keep what each tool returned, so answers can be traced to it
            results += [c["content"] if isinstance(c["content"], str) else "".join(x.get("text", "") for x in c["content"])
                        for c in d["message"].get("content", []) if isinstance(c, dict) and c.get("type") == "tool_result"]
    res["tool_calls"], res["tool_results"], res["key_leaked"] = calls, results, leaked
    res["touched_repo"] = str(ROOT) in json.dumps(calls)  # audit: the raw agent must not read our grid
    shutil.rmtree(cwd, ignore_errors=True)
    (out / f"{name or agent}-r{r}.json").write_text(json.dumps(res, indent=2))
    print(f"{name or agent} r{r}: {res.get('duration_ms', 0) / 1000:.0f}s ${res.get('total_cost_usd', 0):.2f} "
          f"{len(calls)} tool calls{' TOUCHED REPO' if res['touched_repo'] else ''}", flush=True)
    return res


def main() -> None:
    first, last = (int(x) for x in sys.argv[1:3]) if len(sys.argv) > 2 else (1, 3)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = ["| Agent | Round | Time | Cost (API price) | Tool calls | Turns |", "|---|---|---|---|---|---|"]
    for r in range(first, last + 1):
        with ThreadPoolExecutor(3) as pool:
            done = dict(zip(AGENTS, pool.map(lambda a: run(a, r), AGENTS)))
        for agent, res in done.items():
            rows.append(f"| {agent} | {r} | {res.get('duration_ms', 0) / 1000:.0f}s | ${res.get('total_cost_usd', 0):.2f} "
                        f"| {len(res['tool_calls'])} | {res.get('num_turns', '?')} |")
    for r in range(1, first):  # keep earlier rounds in the table
        for agent in AGENTS:
            f = OUT / f"{agent}-r{r}.json"
            if f.exists():
                res = json.loads(f.read_text())
                rows.append(f"| {agent} | {r} | {res.get('duration_ms', 0) / 1000:.0f}s | ${res.get('total_cost_usd', 0):.2f} "
                            f"| {len(res['tool_calls'])} | {res.get('num_turns', '?')} |")
    (OUT / "metrics.md").write_text("# Benchmark metrics\n\n" + f"Question: {QUESTION}\n\n" + "\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
