"""Second hand check (SPEC success 2): count one quarter with plain csv, no DuckDB.

Run: .venv/bin/python scripts/hand_check.py
Must equal the 2023-Q2 'companies' row in active/coverage/coverage.csv.
"""
import csv
import sys
from pathlib import Path

# Written out again on purpose: the check must not share code with coverage.py.
COMPANY_TYPES = {
    "Private Limited Company",
    "Community Interest Company",
    "PRI/LTD BY GUAR/NSC (Private, limited by guarantee, no share capital)",
    "PRI/LBG/NSC (Private, Limited by guarantee, no share capital, use of 'Limited' exemption)",
    "Private Unlimited Company",
    "Public Limited Company",
}
ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data/snapshots/BasicCompanyDataAsOneFile-2026-11-01.csv"

n = 0
with open(SNAPSHOT, newline="", encoding="utf-8") as f:
    reader = csv.reader(f)
    header = [h.strip() for h in next(reader)]
    cat_i, date_i = header.index("CompanyCategory"), header.index("IncorporationDate")
    for row in reader:
        if not row:  # one blank line sits mid-file (where the 7 parts were joined)
            continue
        day, month, year = row[date_i].split("/")
        if year == "2023" and month in ("04", "05", "06") and row[cat_i] in COMPANY_TYPES:
            n += 1
expected = next(int(r["snapshot"]) for r in csv.DictReader(open(ROOT / "active/coverage/coverage.csv"))
                if r["quarter"] == "2023-Q2" and r["type"] == "companies")
print(f"plain csv: {n:,}   query: {expected:,}   {'MATCH' if n == expected else 'MISMATCH'}")
sys.exit(n != expected)
