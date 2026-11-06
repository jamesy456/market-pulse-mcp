"""Testing phase: every number in active/testing/TESTING-RESULTS.md, read from the saved results (nothing typed by hand).

Run: .venv/bin/python scripts/testing_results.py   -> active/testing/numbers.md
Reads: pytest, active/testing/sweep.md, active/testing/check-standouts.md (header line only: it holds exact counts),
active/testing/cases/metrics.md, the blind case scores, active/e2e/results.md (and its committed history),
active/testing/breakit/results.md and the break-it judge's review.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
T, R = ROOT / "active/testing", ROOT / "active/review"


def sh(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout


def tests() -> str:
    return re.search(r"(\d+ passed[^\n]*)", sh(sys.executable, "-m", "pytest", "-q"))[1]


def sweep() -> list[str]:
    s = (T / "sweep.md").read_text()
    return [re.search(r"\d[\d,]* SIC codes and \d+ GB council areas; [\d,]+ answers", s)[0],
            re.search(r"\*\*Problems: \d+\*\*", s)[0]]


def standouts() -> str:
    return next(l for l in (T / "check-standouts.md").read_text().splitlines() if l.startswith("Survival:"))


def medians() -> list[str]:
    m = (T / "cases/metrics.md").read_text().split("| Agent | Runs", 1)[1]
    return ["| Agent | Runs" + m.split("\n\n", 1)[0]]


def scores() -> list[str]:
    return (R / "cases-blind-results.md").read_text().strip().splitlines()[2:]


def e2e() -> list[str]:
    now = re.search(r"\*\*Score: (\d+/\d+)\*\*", (ROOT / "active/e2e/results.md").read_text())[1]
    hist = []
    for h in sh("git", "log", "--format=%h", "--", "active/e2e/results.md").split():
        m = re.search(r"\*\*Score: (\d+/\d+)\*\*", sh("git", "show", f"{h}:active/e2e/results.md"))
        hist.append(f"{h} {m[1] if m else '?'}")
    fails = re.findall(r"### Round (\d): FAIL\n\n\*\*Checks:\*\* ([^\n]*)", (ROOT / "active/e2e/results.md").read_text())
    why = [", ".join(k for k, v in re.findall(r"(\w+)=(\w+)", c) if v == "False" and k != "quoted_verbatim")
           for _, c in fails]
    rounds = len(list((ROOT / "active/e2e").glob("r*q*.json")))
    return [f"Now: {now}, over {rounds} rounds (questions x rounds). Committed history (newest first): {'; '.join(hist)}.",
            f"Failed rounds now: {len(fails)}; failed checks: {why}."]


def breakit() -> list[str]:
    auto = re.findall(r"\*\*Auto:\*\* (\{[^}]*\})", (T / "breakit/results.md").read_text())
    bad = sum("False" in a.replace("'used_tools': False", "") for a in auto)
    j = (R / "codex-breakit-judge.md").read_text()
    verdicts = {v: len(re.findall(rf"\| {v} \|", j)) for v in ("PASS", "PARTIAL", "FAIL")}
    j2 = (R / "codex-breakit-judge-3.md").read_text().split("## Recommended", 1)[0]
    now = {v: len(re.findall(rf"\| B\d+ R\d \| {v} \|", j2)) for v in ("PASS", "PARTIAL", "FAIL")}
    return [f"Latest runs: {len(auto)}; runs failing an automatic check other than used_tools: {bad}; "
            f"runs that used no tool: {sum(chr(39) + 'used_tools' + chr(39) + ': False' in a for a in auto)}.",
            f"Codex judge, first runs (before the break-it fixes): {verdicts}.",
            f"Codex judge, final server (codex-breakit-judge-3.md): {now}; "
            f"{re.search(r'[*][*](HOLDS WITH FIXES|HOLDS|BREAKS)[.]?[*][*]', (R / 'codex-breakit-judge-3.md').read_text())[1]}."]


def missed_standout() -> str:
    """The cost of the every-area bar: the strongest exact-count survival standout in construction, 2023-Q4 to
    2024-Q3, which the tool no longer lists. Prints only a z and an area name (the counts behind it are large)."""
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts"))
    import server
    from check_standouts import exact, q
    from release import odds_z, z_needed
    sics, lo, hi = ["41", "42", "43"], q("2023-Q4"), q("2024-Q3")
    names = dict(server.db().execute("SELECT ladcd, ladnm FROM areas WHERE NOT northern_ireland "
                                     "AND ladcd <> 'unmatched'").fetchall())
    gone, closed, live = (exact(sics, lo, hi, t, a) for t, a in (("grid_closed", "under_1y"), ("grid_closed", None),
                                                                ("grid", None)))
    allr = {k: closed.get(k, 0) + live.get(k, 0) for k in closed.keys() | live.keys()}
    gc, ga = sum(gone.values()), sum(allr.values())
    z, code = max((odds_z(gc - e, ga - gc - (allr[k] - e), e, allr[k] - e), k) for k, e in gone.items()
                  if min(e, allr[k] - e) >= 10)
    listed = server.one_year_survival(sics, "UK", "2023-Q4", "2024-Q3", 25).rows
    return (f"Construction 2023-Q4 to 2024-Q3: strongest exact survival standout {names.get(code, code)}, exact z "
            f"{z:.1f}, bar {z_needed(len(names)):.1f}; listed by the tool: {bool(listed)}.")


def small_in_cases() -> str:
    """The e2e small-count check over every Market Pulse case answer (current server and every earlier one kept)."""
    import json
    sys.path.insert(0, str(ROOT / "scripts"))
    from e2e import SMALL
    files = sorted((T / "cases").glob("mcp-*.json")) + sorted((T / "cases").glob("v*/mcp-*.json"))
    hits = [f"{f.name}: {m.group()!r}" for f in files  # the matched text, so a label ("Caveat 1") shows as one
            for m in SMALL.finditer(json.loads(f.read_text()).get("result", ""))]
    return f"Market Pulse case answers checked for an exact count below 10: {len(files)}; flagged: {hits or 0}."


def quote_failures() -> str:
    """Each summary-form sentence in the final e2e and break-it runs that isn't word for word from the server: in quotation
    marks (a false quote, fails the check) or a rewording without them (not counted as a quote since 2 Nov 2026)."""
    import json
    sys.path.insert(0, str(ROOT / "scripts"))
    from e2e import SUMMARY
    out = []
    for f in sorted((ROOT / "active/e2e").glob("r*q*.json")) + sorted((T / "breakit").glob("b*-r*.json")):
        d = json.loads(f.read_text())
        served, a = " ".join(d.get("tool_results", [])), d.get("result", "")
        for q in SUMMARY.findall(a):
            if q not in served:
                before = a[max(0, a.find(q) - 1):a.find(q)]
                out.append(f"{f.stem}: {'in quotation marks' if before in '\"“' and before else 'rewording, no quotation marks'}")
    return f"Summary-form sentences not word for word: {out or 0}."


def fewer_than_10() -> str:
    return sh(sys.executable, "scripts/check_fewer_than_10.py").strip()


def no_tool_runs() -> str:
    import json
    runs = [f.stem for f in sorted((T / "breakit").glob("b*-r*.json")) if not json.loads(f.read_text()).get("tool_calls")]
    return f"Break-it runs with no tool call: {runs}."


if __name__ == "__main__":
    out = ["# Testing numbers (generated by scripts/testing_results.py; do not edit)", "",
           "## Tests", tests(), "", "## Sweep", *sweep(), "", "## Standouts on exact counts", standouts(), missed_standout(), "",
           "## Case-study medians", *medians(), "", "## Case-study scores", *scores(), "",
           "## End-to-end", *e2e(), "", "## Break-it", *breakit(), no_tool_runs(), "", "## Checks across runs", small_in_cases(), quote_failures(), fewer_than_10(), ""]
    (T / "numbers.md").write_text("\n".join(out))
    print("\n".join(out))
