"""Black-box measurements (code audit): start the real server, speak MCP over stdio, record sizes, times and memory.

Run: .venv/bin/python scripts/measure_tools.py
Uses no key, no network and no AI. Each call runs three times; the slowest time is shown, because the first call on a
cold connection is the one a user waits for. Calls are selected examples, mostly every industry across the UK, plus
two oversized code lists.
"""
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALL, UK = ["all"], "UK"
CALLS = [
    ("find_sic", {"text": "retail"}),
    ("find_area", {"text": "lon"}),
    ("count_incorporations_still_live", {"sic_codes": ALL, "area": UK, "from_quarter": "2021-Q1", "to_quarter": "2025-Q4"}),
    ("count_incorporations_still_live", {"sic_codes": ALL, "area": UK, "from_quarter": "2021-Q1", "to_quarter": "2025-Q4",
                                         "group_by": "quarter", "include_closed": True}),
    ("count_incorporations_still_live", {"sic_codes": ALL, "area": UK, "from_quarter": "2021-Q1", "to_quarter": "2025-Q4",
                                         "group_by": "area", "include_closed": True}),
    ("compare_area_with_great_britain", {"sic_codes": ALL, "area": "E09000012"}),
    ("compare_two_areas", {"sic_codes": ALL, "area": "E09000012", "other_area": "E09000030"}),
    ("rank_areas_against_great_britain", {"sic_codes": ALL, "limit": 25}),
    ("breakdown_by_industry", {"area": UK}),
    ("count_companies_live_now", {"sic_codes": ALL, "area": UK}),
    ("registrations_against_closures", {"sic_codes": ALL}),
    ("largest_areas", {"sic_codes": ALL, "limit": 25}),
    ("largest_industries", {"area": UK, "limit": 25}),
    ("one_year_survival", {"sic_codes": ALL, "area": UK}),
    ("one_year_survival", {"sic_codes": ALL, "limit": 25}),
    # A client can send anything: a long list of the same code, then a long list of bad ones.
    ("count_incorporations_still_live", {"sic_codes": ["62012"] * 20000, "area": UK, "from_quarter": "2021-Q1",
                                         "to_quarter": "2025-Q4"}),
    ("count_incorporations_still_live", {"sic_codes": ["x" * 50] * 20000, "area": UK, "from_quarter": "2021-Q1",
                                         "to_quarter": "2025-Q4"}),
]

t0 = time.perf_counter()
proc = subprocess.Popen([str(ROOT / ".venv/bin/python"), str(ROOT / "src/server.py")], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=ROOT)
seq = 0


def rpc(method: str, params: dict) -> tuple[dict, int, float]:
    global seq
    seq += 1
    start = time.perf_counter()
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": seq, "method": method, "params": params}) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            sys.exit(f"server closed the pipe on {method} {str(params)[:80]}")
        msg = json.loads(line)
        if msg.get("id") == seq:
            return msg, len(line.encode()), time.perf_counter() - start


init, _, _ = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                "clientInfo": {"name": "measure", "version": "0"}})
proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
proc.stdin.flush()
print(f"start to ready: {time.perf_counter() - t0:.2f} s")
print(f"instructions: {len(init['result'].get('instructions', '').encode()):,} bytes")
tools, size, _ = rpc("tools/list", {})
print(f"tools/list: {len(tools['result']['tools'])} tools, {size:,} bytes (sent to the model in every conversation)\n")
print("| Tool | Input | Slowest of 3 | Bytes | Result |\n|---|---|---|---|---|")
for name, args in CALLS:
    worst, size, msg = 0.0, 0, {}
    for _ in range(3):
        msg, size, took = rpc("tools/call", {"name": name, "arguments": args})
        worst = max(worst, took)
    res = msg.get("result", {})
    text = res.get("content", [{}])[0].get("text", "")[:40] if res.get("isError") else "ok"
    shown = {k: (f"{len(v)} items" if isinstance(v, list) and len(v) > 3 else v) for k, v in args.items()}
    print(f"| {name} | {json.dumps(shown)[:70]} | {worst:.3f} s | {size:,} | {text or msg.get('error', '')} |")
proc.stdin.close()
proc.wait(10)
print(f"\nserver peak memory: {resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024 / 1024:.0f} MB, exit code {proc.returncode}")
