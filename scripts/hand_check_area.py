"""Hand check for the grid: Leeds, 2026 Q3, all SICs, private limited, mass postcodes excluded.

Plain csv, no DuckDB, no code shared with build_grid.py.
Run: .venv/bin/python scripts/hand_check_area.py
"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb  # only to read the grid's answer

ROOT = Path(__file__).resolve().parent.parent
LEEDS = "E08000035"
PRIVATE = {"Private Limited Company",
           "PRI/LTD BY GUAR/NSC (Private, limited by guarantee, no share capital)",
           "PRI/LBG/NSC (Private, Limited by guarantee, no share capital, use of 'Limited' exemption)"}
tidy = lambda s: re.sub(r"[^A-Z0-9]", "", s.upper())

leeds_pcs = set()
with open(ROOT / "data/lookup/PCD_OA21_LSOA21_MSOA21_LAD_AUG26_UK_LU.csv", newline="") as f:
    for r in csv.DictReader(f):
        if r["ladcd"] == LEEDS:
            leeds_pcs.add(tidy(r["pcds"]))

per_pc, hits = Counter(), []
with open(ROOT / "data/snapshots/BasicCompanyDataAsOneFile-2026-11-01.csv", newline="", encoding="utf-8") as f:
    reader = csv.reader(f)
    h = [x.strip() for x in next(reader)]
    pc_i, cat_i, d_i = h.index("RegAddress.PostCode"), h.index("CompanyCategory"), h.index("IncorporationDate")
    for row in reader:
        if not row:
            continue
        pc = tidy(row[pc_i])
        if pc:
            per_pc[pc] += 1
        _, m, y = row[d_i].split("/")
        if y == "2026" and m in ("07", "08", "09") and row[cat_i] in PRIVATE and pc in leeds_pcs:
            hits.append(pc)
n = sum(1 for pc in hits if per_pc[pc] < 500)

grid = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True).execute(
    "SELECT sum(companies) FROM grid WHERE ladcd = ? AND year = 2026 AND quarter = 3 "
    "AND type_group = 'private_limited' AND NOT mass_postcode", [LEEDS]).fetchone()[0]
print(f"plain csv: {n:,}   grid: {grid:,}   {'MATCH' if n == grid else 'MISMATCH'}")
sys.exit(n != grid)
