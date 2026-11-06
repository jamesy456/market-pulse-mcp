"""Coverage chart: share of each quarter's new companies still live in the snapshot.

Run after coverage.py: .venv/bin/python scripts/chart.py
Writes active/coverage/coverage_chart.html (self-contained, no libraries).
"""
import csv
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rows = [r for r in csv.DictReader(open(ROOT / "active/coverage/coverage.csv")) if r["type"] == "companies"]
OUT = ROOT / "active/coverage/coverage_chart.html"

W, H, L, R, T, B = 760, 380, 52, 64, 24, 52  # size and margins
pw, ph = W - L - R, H - T - B
x = lambda i: L + pw * i / (len(rows) - 1)
y = lambda pct: T + ph * (1 - pct / 100)
pts = [(x(i), y(float(r["coverage_pct"]))) for i, r in enumerate(rows)]

svg = []
for pct in (0, 25, 50, 75, 100):  # recessive grid
    svg.append(f'<line class="grid" x1="{L}" x2="{W-R}" y1="{y(pct)}" y2="{y(pct)}"/>'
               f'<text class="axis" x="{L-8}" y="{y(pct)+4}" text-anchor="end">{pct}%</text>')
for i, r in enumerate(rows):
    if r["quarter"].endswith("Q1"):
        svg.append(f'<text class="axis" x="{x(i)}" y="{H-B+20}" text-anchor="middle">{r["quarter"][:4]}</text>')
first_new = next(i for i, r in enumerate(rows) if r["method"] == "new")
mx = (x(first_new - 1) + x(first_new)) / 2
svg.append(f'<line class="rule" x1="{mx}" x2="{mx}" y1="{T}" y2="{H-B}"/>'
           f'<text class="note" x="{mx-6}" y="{y(20)}" text-anchor="end">old method ◂</text>'
           f'<text class="note" x="{mx+6}" y="{y(20)}">▸ new</text>')
svg.append('<polyline class="line" points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>')
for (a, b), r in zip(pts, rows):
    tip = html.escape(f'{r["quarter"]}: {int(r["snapshot"]):,} of {int(r["official"]):,} still live '
                      f'({r["coverage_pct"]}%, {r["method"]} method)')
    svg.append(f'<g class="pt" data-tip="{tip}"><circle class="hit" cx="{a}" cy="{b}" r="12"/>'
               f'<circle class="dot" cx="{a}" cy="{b}" r="4"/></g>')
for i in (0, len(rows) - 1):  # selective direct labels: first and last only
    a, b = pts[i]
    svg.append(f'<text class="label" x="{a + (8 if i else -2)}" y="{b - 10}" '
               f'text-anchor="{"start" if i else "start"}">{rows[i]["coverage_pct"]}%</text>')

table = "".join(f'<tr><td>{r["quarter"]}</td><td>{int(r["snapshot"]):,}</td><td>{int(r["official"]):,}</td>'
                f'<td>{r["coverage_pct"]}%</td><td>{r["method"]}</td></tr>' for r in rows)
OUT.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Company survival curve</title>
<style>
:root {{ --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --grid:#e4e3df; --series:#2a78d6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --surface:#1a1a19; --ink:#f0efec; --ink2:#c3c2b7; --grid:#33332f; --series:#3987e5; }} }}
body {{ margin:0; padding:24px 16px; background:var(--surface); color:var(--ink); font:15px/1.45 system-ui,sans-serif; }}
main {{ max-width:760px; margin:auto; }} h1 {{ font-size:20px; margin:0 0 4px; }} p {{ color:var(--ink2); margin:0 0 12px; }}
svg {{ width:100%; height:auto; overflow:visible; }} .grid {{ stroke:var(--grid); }}
.axis,.note {{ fill:var(--ink2); font-size:12px; }} .label {{ fill:var(--ink); font-size:13px; font-weight:600; }}
.rule {{ stroke:var(--ink2); stroke-dasharray:3 4; }} .line {{ fill:none; stroke:var(--series); stroke-width:2; }}
.dot {{ fill:var(--series); stroke:var(--surface); stroke-width:2; }} .hit {{ fill:transparent; }}
.pt:hover .dot {{ r:6; }} #tip {{ position:fixed; pointer-events:none; background:var(--ink); color:var(--surface);
  padding:6px 8px; border-radius:6px; font-size:13px; display:none; }}
table {{ border-collapse:collapse; font-size:13px; margin-top:8px; }} td,th {{ padding:2px 12px 2px 0; text-align:right; }}
td:first-child,th:first-child {{ text-align:left; }} summary {{ cursor:pointer; color:var(--ink2); margin-top:12px; }}
</style></head><body><main>
<h1>Fewer than 4 in 10 companies registered in 2021 still appear in the data</h1>
<p>Companies registered each quarter that are still live in the Companies House snapshot of 1 Nov 2026, as a share of
the official incorporation count for that quarter. UK companies; LLPs, partnerships and charities are left out.</p>
<svg viewBox="0 0 {W} {H}" role="img" aria-label="Line chart: share still live rises from {rows[0]['coverage_pct']}% in {rows[0]['quarter']} to {rows[-1]['coverage_pct']}% in {rows[-1]['quarter']}">
{''.join(svg)}</svg>
<p>Source: Companies House Free Company Data Product (1 Nov 2026) and Incorporated Companies in the UK statistics.
The official method changed in April 2026.</p>
<details><summary>Show the table</summary><table><tr><th>Quarter</th><th>Still live</th><th>Official</th><th>Share</th><th>Method</th></tr>
{table}</table></details></main><div id="tip"></div>
<script>
const tip = document.getElementById('tip');
document.querySelectorAll('.pt').forEach(g => {{
  g.addEventListener('mousemove', e => {{ tip.textContent = g.dataset.tip; tip.style.display = 'block';
    tip.style.left = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (e.clientY - 36) + 'px'; }});
  g.addEventListener('mouseleave', () => tip.style.display = 'none');
}});
</script></body></html>""")
print(f"wrote {OUT}")
