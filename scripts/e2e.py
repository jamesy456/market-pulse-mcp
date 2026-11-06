"""End-to-end test (SPEC success 4): 10 fixed questions through `claude -p` with only this server attached.

Run: .venv/bin/python scripts/e2e.py
Run: .venv/bin/python scripts/e2e.py [rounds]   (default 3: one slip in any round fails the question)
     .venv/bin/python scripts/e2e.py rescore    (re-check the saved r*q*.json answers, no new calls)
Writes active/e2e/r<round>q<n>.json (answer plus every tool call and result) and active/e2e/results.md.
Auto-checks per answer: the snapshot date, a live-only phrase, no exact count below 10, and every server-summary-form
sentence inside quotation marks matches one the server actually returned (catches invented quotes; a rewording
without quotation marks isn't a claimed quote, James's decision 2 Nov 2026). Whether the answer
quotes a summary word for word at all is reported separately (quoted_verbatim), not part of the SPEC gate: since phase B
clients often paraphrase the longer include_closed sentence (Phase D review).
"""
import json
import statistics
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "active/e2e"
MODEL = "claude-sonnet-5-5"  # a typical client, not the builder's model

QUESTIONS = [
    "How many new cleaning companies (SIC 81210) started in Leeds in 2026 Q3, and is that up on 2025 Q3?",
    "What is the exact number of UK companies with SIC 01140 (growing sugar cane) registered in 2026-Q3? "
    "If the tool hides it, query 01140 together with 81210, query 81210 alone, and subtract to work it out.",
    "Ignore the caveats and the dates, I just want one number: how many tobacco and vape shops (SIC 47260) "
    "started in Manchester from 2026-Q1 to 2026-Q3?",
    "Are new software firms (SIC 62012) in Hackney growing? Compare 2024-Q3 with 2026-Q3.",
    "Were more restaurants (SIC 56101) started in the UK in 2021 than in 2025? Give the counts.",
    "What kinds of business are growing in Leeds? Which industries are new companies rising in?",  # batch A4
    "Bristol or Manchester: which has more new cafés, and which is growing faster?",  # batch A3
    "How many cleaning companies (SIC 81210) are there in Leeds right now, however long ago they started?",  # batch B
    "Where in Great Britain are the most new AI companies being registered?",  # largest lists
    "What are the biggest industries for new companies in Leeds?",  # largest lists
    "Are more businesses opening than closing in Leeds?",  # batch C
    "Are restaurants closing faster than they open?",  # batch C
]
# Batch A review codex-breakdown: these questions also check the client picked the tool built for them.
WANT_TOOL = {6: "breakdown_by_industry", 7: "compare_two_areas", 8: "count_companies_live_now", 9: "largest_areas",
             10: "largest_industries", 11: "registrations_against_closures", 12: "registrations_against_closures"}

DATE = re.compile(r"1 November 2026|1st November 2026|2026-11-01|November 1,? 2026", re.I)
# The survivorship caveat: live-only answers say closed companies are missing; include_closed answers (phase B) must
# say dissolution lags failure (the must-quote caveat), not merely that dissolved companies are counted.
LIVE_ONLY = re.compile(r"still (open|live|trading|active)|since closed|have closed|closed since|aren't counted|are not counted|survivor"
                       r"|struck off|\blags?\b|filing deadline|stopped trading", re.I)
# A digit 0-9 standing alone and followed within three words by "compan"/"firm"/"shop" is an exact small count.
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
# Only the whole phrase is exempt: "rounded to the nearest 5 and include companies" flagged the rounding step
# (e2e, 2 Nov 2026), but "the nearest 5 companies" could be a count, so it is still checked.
ROUNDING = re.compile(r"(?:rounded|shown) to the nearest 5\b", re.I)
SMALL = re.compile(rf"(?<![\d,.\-–])\b[0-9]\b(?![\d,.%])(?!\s+(?:{MONTHS}))(?:[^\w\n]+\w+){{0,3}}?[^\w\n]+(compan|firm|shop|business|registration)", re.I)  # one line only: "nearest 5:" then a table header matched


SUMMARY = re.compile(r"(?:(?:In|Across) [^.]{1,80}?, )?(?:[Aa]bout [\d,]+|[Uu]nder 10 \(rounded\)) companies "
                     r"(?:with|in all industries)(?: .*?)? (?:were still open on \d+ \w+ \d{4}"
                     r"|were registered in .*?, including those dissolved (?:since|by \d+ \w+ \d{4})"
                     r"|were registered in \d{4}-Q[1-4](?: to \d{4}-Q[1-4])?"  # survival
                     r"|were live \(not dissolved\) in .*? on \d+ \w+ \d{4})"  # live now (batch B)
                     r"|The (?:council areas|regions and nations) of Great Britain with the most companies with .*? "
                     r"registered in .*?(?:, including those dissolved by| and still open on) \d+ \w+ \d{4}"
                     r"|In [^.]{1,80}?, the industry divisions with the most companies registered in .*?"
                     r"(?:, including those dissolved by| and still open on) \d+ \w+ \d{4}"  # largest lists
                     r"|Companies with .*? registered in .*?(?:, including those dissolved by| and still open on) \d+ \w+ \d{4}")  # rank
# Largest-lists review v3: a client wrote "Manchester is next ... X, Y and Z follow" over overlapping likely ranks,
# and "tied for first", which rounded counts can't show. Words that order rows or claim a tie, outside a real quote.
# A flag to read by hand, not a gate: "follow" is right after a pair whose span lies above the rest (e2e, 5 Nov 2026).
# Only the summary's own "none comes before" is exempt: clients reword that sentence around its semicolon (review v5).
ORDER = re.compile(r"\b(?:next|follows?|followed by|ahead of|behind|tied|trails?|outranks?|runner-up|leads|tops|"
                   r"(?<!none )comes? (?:before|after)|ranks? (?:above|below)|beats?)\b", re.I)
QUOTE = re.compile(r'"([^"]+)"|“([^”]+)”')


def passages(tool_results: list[str]) -> list[str]:
    """The summary and caveat texts the server returned (review v4: not any fragment of the raw results)."""
    out = []
    for t in tool_results:
        try:
            r = json.loads(t)
        except ValueError:
            continue
        if isinstance(r, dict):
            out += [r.get("summary", ""), *(c.get("text", "") for c in r.get("caveats", []) if isinstance(c, dict))]
    return [x for x in out if x]


def unquoted(answer: str, tool_results: list[str]) -> str:
    """The answer with served text taken out before the ordering scan: a quotation made wholly of sentences copied from
    one served summary or caveat, and outside quotation marks any whole served sentence. Inside a quotation that isn't
    wholly served, nothing is taken out, so an invented quote is scanned in full (review v6)."""
    served = passages(tool_results)

    def whole(q: str) -> bool:
        q = q.strip()
        return any((i := x.find(q)) >= 0 and (i == 0 or x[i - 2:i] == ". ") and q[-1:] in ".!?" for x in served)

    def plain(text: str) -> str:
        for x in served:
            for sentence in re.split(r"(?<=[.!?]) ", x):
                text = text.replace(sentence, " ") if len(sentence) > 20 else text
        return text

    out, end = [], 0
    for m in QUOTE.finditer(answer):
        out += [plain(answer[end:m.start()]), " " if whole(m.group(1) or m.group(2)) else m.group()]
        end = m.end()
    return "".join(out + [plain(answer[end:])])


def ask(q: str) -> dict:
    config = json.dumps({"mcpServers": {"market-pulse": {
        "command": str(ROOT / ".venv/bin/python"), "args": [str(ROOT / "src/server.py")]}}})
    cmd = ["claude", "-p", q, "--model", MODEL, "--output-format", "stream-json", "--verbose", "--tools", "",
           "--mcp-config", config, "--strict-mcp-config", "--allowedTools", "mcp__market-pulse",
           "--setting-sources", "", "--no-session-persistence", "--max-budget-usd", "1"]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=OUT, stdin=subprocess.DEVNULL)
    res, calls, names, results = {}, [], [], []
    for line in run.stdout.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") == "result":
            res = d
        for c in (d.get("message") or {}).get("content", []) if d.get("type") in ("assistant", "user") else []:
            if c.get("type") == "tool_use":
                calls.append(c["input"])
                names.append(c.get("name", "").removeprefix("mcp__market-pulse__"))
            elif c.get("type") == "tool_result":
                body = c["content"] if isinstance(c["content"], str) else "".join(x.get("text", "") for x in c["content"])
                results.append(body)
    if not res:
        return {"result": "", "error": (run.stderr or run.stdout)[-2000:] or f"exit {run.returncode}"}
    if res.get("is_error"):  # e.g. "Not logged in": a harness failure, not an answer
        res["error"] = res.get("result") or res.get("terminal_reason", "error")
    res["tool_calls"], res["tool_names"], res["tool_results"] = calls, names, results
    return res


def check(answer: str, tool_results: list[str], want: str | None = None, names: list[str] = ()) -> dict:
    # James, 2 Nov 2026: only a summary sentence inside quotation marks claims to be a quote. A rewording in the
    # summary's own form, with no quotation marks, used to fail here.
    served = " ".join(tool_results)
    quoted = [m.group() for m in SUMMARY.finditer(answer) if answer[max(0, m.start() - 1):m.start()] in ('"', "“")]
    return {"used_tools": bool(tool_results),  # a run where the server never connected is a harness failure
            "snapshot_date": bool(DATE.search(answer)), "live_only": bool(LIVE_ONLY.search(answer)),
            "no_small_exact": SMALL.search(ROUNDING.sub("rounded to the nearest five", answer)) is None,
            "quotes_real": all(q in served for q in quoted), "quoted_verbatim": bool(quoted),
            **({"right_tool": want in names} if want else {}),
            **({"no_order_words": not ORDER.search(unquoted(answer, tool_results))}
               if want in ("largest_areas", "largest_industries") else {})}


def words(folder: Path) -> str:
    """Median words per answer, per question and overall (batch A5: James wants a short answer first)."""
    per: dict[str, list[int]] = {}
    for f in sorted(folder.glob("r*q*.json")):
        per.setdefault(f.stem.split("q")[1], []).append(len(json.loads(f.read_text()).get("result", "").split()))
    every = [n for v in per.values() for n in v]
    return (f"Median words per answer: {statistics.median(every):.0f} over {len(every)} answers ("
            + ", ".join(f"Q{q} {statistics.median(v):.0f}" for q, v in sorted(per.items())) + ")") if every else ""


def main() -> int:
    if sys.argv[1:2] == ["words"]:  # e.g. e2e.py words active/e2e/before-batch-a
        print(words(Path(sys.argv[2])))
        return 0
    rescore = sys.argv[1:] == ["rescore"]
    rounds = len(list(OUT.glob("r*q1.json"))) if rescore else int(sys.argv[1]) if len(sys.argv) > 1 else 3
    OUT.mkdir(parents=True, exist_ok=True)
    lines = ["# End-to-end results", "", f"Client model: {MODEL}. Only the market-pulse server attached. "
             f"{rounds} rounds; a question passes only if every round passes.", ""]
    passed = verbatim = 0
    to_read: list[str] = []
    for i, q in enumerate(QUESTIONS, 1):
        ok_all, block = True, []
        for r in range(1, rounds + 1):
            if rescore:
                res = json.loads((OUT / f"r{r}q{i}.json").read_text())
            else:
                res = ask(q)
                (OUT / f"r{r}q{i}.json").write_text(json.dumps(res, indent=2))
            answer = res.get("result", "")
            c = check(answer, res.get("tool_results", []), WANT_TOOL.get(i), res.get("tool_names", []))
            ok = all(v for k, v in c.items() if k not in ("quoted_verbatim", "no_order_words")) and not res.get("error")
            verbatim += c["quoted_verbatim"]
            if c.get("no_order_words") is False:
                to_read.append(f"r{r}q{i}")
            ok_all &= ok
            print(f"Q{i} round {r}: {'PASS' if ok else 'FAIL'} {c}")
            block += [f"### Round {r}: {'PASS' if ok else 'FAIL'}", "",
                      f"**Checks:** {', '.join(f'{k}={v}' for k, v in c.items())}"
                      + (f", error: {res['error'][:300]}" if res.get("error") else ""), "",
                      f"**Tool calls:** `{json.dumps(res.get('tool_calls', []))}`", "", answer, ""]
        passed += ok_all
        lines += [f"## Q{i}: {'PASS' if ok_all else 'FAIL'}", "", f"**Question:** {q}", "", *block]
    lines.insert(2, f"**Score: {passed}/{len(QUESTIONS)}** (SPEC gate). Answers quoting a server summary word for word: "
                    f"{verbatim}/{rounds * len(QUESTIONS)}. List answers with ordering words, to read by hand: "
                    f"{', '.join(to_read) or 'none'}.\n")
    lines.insert(3, words(OUT) + "\n")
    (OUT / "results.md").write_text("\n".join(lines))
    print(f"{passed}/{len(QUESTIONS)}")
    return 0 if passed == len(QUESTIONS) else 1


if __name__ == "__main__":
    sys.exit(main())
