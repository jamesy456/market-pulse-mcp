"""Blind scoring of the case-study comparison: hide which tool wrote each answer, then total the scores.

sample, agree: a second scorer on a random 5 answers per arm, then line-by-line agreement.
make:  shuffles each case's answers under random ids -> active/.tmp/blind/c<n>.md, key.json (git-ignored)
tally: reads the scorers' SCORE lines from active/.tmp/blind/scores-c<n>.md -> active/.tmp/blind/tally.md
Style can still give a tool away (quoted caveats, cited pages); this hides the labels, not the voice.
"""
import json
import re
import secrets
import sys
from pathlib import Path

from cases import CASES, OUT, ROOT, ROUNDS

BLIND = ROOT / "active/.tmp/blind"
ARMS = ("mcp", "web", "ch", "mcp_b", "mcp_c")
NAMES = re.compile(r"(?i)market[ -]?pulse|companies[- ]house[- ]mcp|ch-search|mcp__\S+|\bMCP\b|web ?search")


def make() -> None:
    BLIND.mkdir(parents=True, exist_ok=True)
    key = {}
    for c, question in CASES.items():
        runs = [(a, r) for a in ARMS for r in ROUNDS]
        secrets.SystemRandom().shuffle(runs)
        parts = [f"# {c}\n\n**Question:** {question}\n"]
        for i, (a, r) in enumerate(runs, 1):
            rid = f"{c}-{i:02d}"
            key[rid] = {"arm": a, "round": r, "case": c}
            answer = NAMES.sub("[tool]", json.loads((OUT / f"{a}-{c}-r{r}.json").read_text())["result"] or "(no answer)")
            parts.append(f"\n---\n\n## Answer {rid}\n\n{answer}\n")
        (BLIND / f"{c}.md").write_text("".join(parts))
    (BLIND / "key.json").write_text(json.dumps(key, indent=1))
    print(len(key), "answers blinded")


def tally() -> None:
    key = json.loads((BLIND / "key.json").read_text())
    seen = scores(BLIND.glob("scores-c*.md"))
    missing = sorted(set(key) - set(seen))
    assert not missing and not set(seen) - set(key), f"missing {missing}"
    out = ["| Arm | Runs | Points | Applicable lines | Mean per run | R1 | R2 | R3 | R4 | R5 | R6 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in ARMS:
        rows = [v for k, v in seen.items() if key[k]["arm"] == a]
        pts = sum(x == "1" for v in rows for x in v)
        app = sum(x in "01" for v in rows for x in v)
        lines = [f"{sum(v[i] == '1' for v in rows)}/{sum(v[i] in '01' for v in rows)}" for i in range(6)]
        out.append(f"| {a} | {len(rows)} | {pts} | {app} | {pts / len(rows):.2f} | " + " | ".join(lines) + " |")
    out += ["", "| Arm | " + " | ".join(CASES) + " |", "|---|" + "---|" * len(CASES)]
    for a in ARMS:
        out.append(f"| {a} | " + " | ".join(str(sum(x == "1" for k, v in seen.items() if key[k]["arm"] == a and key[k]["case"] == c for x in v)) for c in CASES) + " |")
    (BLIND / "tally.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


def sample() -> None:
    """A random 5 answers per arm for a second scorer, who never sees the first scores."""
    key = json.loads((BLIND / "key.json").read_text())
    rng = secrets.SystemRandom()
    ids = sorted(i for a in ARMS for i in rng.sample([k for k, v in key.items() if v["arm"] == a], 5))
    parts = []
    for c, question in CASES.items():
        text = (BLIND / f"{c}.md").read_text()
        keep = [p for p in text.split("\n---\n\n")[1:] if p.split()[2] in ids]
        if keep:
            parts.append(f"# {c}\n\n**Question:** {question}\n\n" + "\n---\n\n".join(keep))
    (BLIND / "sample.md").write_text("\n\n".join(parts))
    (BLIND / "sample-ids.json").write_text(json.dumps(ids))
    print(len(ids), "answers in the sample")


def scores(files) -> dict:
    found = {}
    for f in files:
        for line in f.read_text().splitlines():
            if line.startswith("SCORE"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                assert len(cells) == 8 and cells[0] == "SCORE" and re.fullmatch(r"c\d-\d\d", cells[1]), f"bad line: {line}"
                assert cells[1] not in found, f"scored twice: {cells[1]}"
                assert set(cells[2:]) <= {"0", "1", "n/a"}, f"bad mark: {line}"
                found[cells[1]] = cells[2:]
    return found


def agree() -> None:
    first, second = scores(BLIND.glob("scores-c*.md")), scores([BLIND / "scores-sample.md"])
    ids = json.loads((BLIND / "sample-ids.json").read_text())
    assert sorted(second) == sorted(ids), "second scorer's ids differ from the sample"
    pairs = [(i, n, x, y) for i in ids for n, (x, y) in enumerate(zip(first[i], second[i]), 1)]
    same = [p for p in pairs if p[2] == p[3]]
    print(f"{len(same)} of {len(pairs)} line scores agree; totals {sum(p[2] == '1' for p in pairs)} first, {sum(p[3] == '1' for p in pairs)} second")
    for p in pairs:
        if p[2] != p[3]:
            print(f"  {p[0]} R{p[1]}: {p[2]} -> {p[3]}")


if __name__ == "__main__":
    {"make": make, "tally": tally, "sample": sample, "agree": agree}[sys.argv[1]]()
