"""Quarterly coverage: snapshot count / official Companies House incorporations.

Run: .venv/bin/python scripts/coverage.py
Writes active/coverage/coverage.csv and prints the table.
"""
import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data/snapshots/BasicCompanyDataAsOneFile-2026-11-01.csv"
OLD = ROOT / "data/official/incorporated_2026Q1_oldmethod.csv"  # quarterly, to Mar 2026
NEW = ROOT / "data/official/incorporated_2026Q3.csv"  # monthly, Apr-Sep 2026
OUT = ROOT / "active/coverage/coverage.csv"

# Snapshot categories matched to the official "All companies" line (DECISIONS.md, 1 Nov).
# Charities, LLPs, LPs, overseas entities and registered societies are left out.
COMPANY_TYPES = [
    "Private Limited Company",
    "Community Interest Company",
    "PRI/LTD BY GUAR/NSC (Private, limited by guarantee, no share capital)",
    "PRI/LBG/NSC (Private, Limited by guarantee, no share capital, use of 'Limited' exemption)",
    "Private Unlimited Company",
    "Public Limited Company",
]
LLP = "Limited Liability Partnership"
FROM_YEAR = 2021

con = duckdb.connect()
con.execute(f"""
    CREATE TABLE companies AS
    SELECT CompanyNumber AS company_number, CompanyCategory AS category,
           CompanyStatus AS status, IncorporationDate AS inc_date_text
    FROM read_csv('{SNAPSHOT}', all_varchar=true)
""")
counts = con.execute((ROOT / "sql/first_count.sql").read_text()).fetchall()
ours = {}  # (year, quarter, "companies"|"llp") -> count
for year, q, cat, n in counts:
    kind = "companies" if cat in COMPANY_TYPES else "llp" if cat == LLP else None
    if kind:
        ours[(year, q, kind)] = ours.get((year, q, kind), 0) + n

official = {}  # (year, quarter, kind) -> (count, method)
for r in csv.DictReader(open(OLD, encoding="utf-8-sig")):
    if r["Region"] != "UK" or r["Attribute"] != "Incorporations":
        continue
    kind = {"All companies": "companies", "Limited liability partnerships": "llp"}.get(r["Corporate body type"])
    if not kind:
        continue
    d, m, y = r["Date"].split("/")  # Date is the quarter end, e.g. 31/03/2026
    official[(int(y), (int(m) - 1) // 3 + 1, kind)] = (int(r["Value"]), "old")
new = {}  # monthly rows summed to quarters
new_kind = {"All Companies": "companies", "LLPs": "llp"}
for r in csv.DictReader(open(NEW, encoding="utf-8-sig")):
    kind = new_kind.get(r["Corporate Bodies"])
    if r["Geography"] != "UK" or r["Attribute"] != "Incorporations" or r["Route"] != "Total" or not kind:
        continue
    month = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"].index(r["Month"]) + 1
    key = (int(r["Calendar Year"]), (month - 1) // 3 + 1, kind)
    new[key] = new.get(key, 0) + int(r["Value"])
official.update({k: (v, "new") for k, v in new.items()})

rows = []
for (y, q, kind), (off, method) in sorted(official.items()):
    if y < FROM_YEAR:
        continue
    n = ours.get((y, q, kind), 0)
    rows.append({"quarter": f"{y}-Q{q}", "type": kind, "method": method,
                 "snapshot": n, "official": off, "coverage_pct": round(100 * n / off, 1)})

OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)
for r in rows:
    flag = "  <-- over 100%" if r["coverage_pct"] > 100 else ""
    print(f"{r['quarter']}  {r['type']:9} {r['method']}  {r['snapshot']:>8,} / {r['official']:>8,} = {r['coverage_pct']:5.1f}%{flag}")

# Hour-12 kill check (SPEC success 1): latest complete quarter 90-102%, and no quarter above 102%.
latest = [r for r in rows if r["type"] == "companies"][-1]
over = [f"{r['quarter']} {r['type']}" for r in rows if r["coverage_pct"] > 102]
ok = 90 <= latest["coverage_pct"] <= 102 and not over
print(f"\nKILL CHECK {'PASS' if ok else 'FAIL'}: latest {latest['quarter']} = {latest['coverage_pct']}%,"
      f" quarters over 102%: {over or 'none'}")
raise SystemExit(0 if ok else 1)
