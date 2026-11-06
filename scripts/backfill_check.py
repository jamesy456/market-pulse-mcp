"""Check the backfill: per quarter, snapshot + backfilled closed companies should equal the official total.

Run: .venv/bin/python scripts/backfill_check.py
Fails if any day from 2021-01-01 to 2026-10-31 is missing from the manifest or its file has the wrong row count,
any quarter from 2021-Q1 to 2026-Q3 is missing, any date doesn't parse, or any quarter is more than 0.03% off
(the gate's worst quarter was 0.017%). Closed companies already in the snapshot would be double-counted, so
they are matched by company number and left out. (A cessation-date rule was wrong: companies with a future
cessation date, e.g. a strike-off gazetted for 3 Nov, are already gone from the 1 Nov snapshot. DECISIONS, 2 Nov.) Types outside the gate's list are reported, never silently dropped.
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backfill_closed import FIRST, LAST, MANIFEST, OUT  # noqa: E402
from closed_check import TYPES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_CSV = ROOT / "data/snapshots/BasicCompanyDataAsOneFile-2026-11-01.csv"
TOLERANCE = 0.0003
# Accepted by James, 2 Nov 2026: the API's own hits equal the download, so the gap is register vs official
# statistic, not download. Pinned to the exact shortfall: any other value for this quarter fails again.
KNOWN_GAPS = {"2023-Q2": 178}

hits = {m["day"]: m["hits"] for m in map(json.loads, MANIFEST.read_text().splitlines())}
days = [FIRST + timedelta(n) for n in range((LAST - FIRST).days + 1)]
missing = [d for d in days if d.isoformat() not in hits or not (OUT / f"{d}.jsonl").exists()
           or sum(1 for _ in open(OUT / f"{d}.jsonl")) != hits[d.isoformat()]]
if missing:
    sys.exit(f"{len(missing)} days missing or incomplete, first {missing[0]}")

con = duckdb.connect()
con.execute(rf"""CREATE TABLE closed AS SELECT upper(trim(company_number)) AS company_number, COALESCE(company_type, '(missing)') AS company_type, CAST(date_of_creation AS DATE) AS born,
    CAST(date_of_cessation AS DATE) AS died, regexp_extract(filename, '(\d{{4}}-\d{{2}}-\d{{2}})\.jsonl$', 1) AS file_day
    FROM read_json('{OUT}/*.jsonl', format='newline_delimited', filename=true,
                   columns={{company_number: 'VARCHAR', company_type: 'VARCHAR', date_of_creation: 'VARCHAR', date_of_cessation: 'VARCHAR'}})""")
# CAST (not TRY_CAST) already fails on a malformed date; a null one is caught here.
if con.execute("SELECT count(*) FROM closed WHERE born IS NULL OR died IS NULL").fetchone()[0]:
    sys.exit("rows with a missing incorporation or cessation date")
rows, unique, blank, misplaced = con.execute("""SELECT count(*), count(DISTINCT company_number),
    count(*) FILTER (company_number IS NULL), count(*) FILTER (CAST(born AS VARCHAR) != file_day) FROM closed""").fetchone()
if blank:
    sys.exit(f"{blank:,} rows without a company number")
if rows != unique:  # Codex re-review: a duplicated day file shows up here
    sys.exit(f"{rows - unique:,} duplicate company numbers across day files")
if misplaced:  # Codex re-review 2: content check, every row must belong to the day its file is named after
    sys.exit(f"{misplaced:,} rows whose incorporation date doesn't match their day file")
con.execute(f"CREATE TABLE live AS SELECT upper(trim(CompanyNumber)) AS n FROM read_csv('{SNAPSHOT_CSV}', "
            "header=true, all_varchar=true)")  # Codex reviews 4-5: same form both sides, normalised before any check
odd = con.execute("""SELECT (SELECT count(*) FROM live WHERE n IS NULL OR NOT regexp_full_match(n, '[A-Z0-9]{8}')),
    (SELECT count(*) FROM closed WHERE NOT regexp_full_match(company_number, '[A-Z0-9]{8}'))""").fetchone()
if any(odd):
    sys.exit(f"company numbers not 8 letters/digits: snapshot {odd[0]:,}, closed {odd[1]:,}")
overlap = con.execute("SELECT count(*) FROM closed c WHERE EXISTS (SELECT 1 FROM live l WHERE l.n = c.company_number)"
                      ).fetchone()[0]
print(f"closed companies also in the snapshot (left out): {overlap:,}")
for t, n in con.execute("SELECT company_type, count(*) FROM closed WHERE company_type NOT IN "
                        f"({','.join('?' * len(TYPES))}) GROUP BY 1 ORDER BY 2 DESC", TYPES).fetchall():
    print(f"not counted (outside the gate's types): {t} {n:,}")
got = dict(con.execute(f"""SELECT strftime(born, '%Y') || '-Q' || quarter(born), count(*) FROM closed
    WHERE company_type IN ({','.join('?' * len(TYPES))})
      AND NOT EXISTS (SELECT 1 FROM live l WHERE l.n = closed.company_number)  -- NOT IN breaks on a NULL
    GROUP BY 1""", TYPES).fetchall())
expected = {f"{y}-Q{q}" for y in range(2021, 2027) for q in range(1, 5)} - {"2026-Q4"}
bad = sorted(expected - set(got))
official_rows = [r for r in csv.DictReader(open(ROOT / "active/coverage/coverage.csv"))
                 if r["type"] == "companies" and r["quarter"] in expected]
if sorted(r["quarter"] for r in official_rows) != sorted(expected):  # Codex re-review: exactly one row per quarter
    sys.exit("coverage.csv must have exactly one companies row per quarter 2021-Q1 to 2026-Q3")
for r in official_rows:
    snap, official, closed = int(r["snapshot"]), int(r["official"]), got.get(r["quarter"], 0)
    gap = (snap + closed) / official - 1
    short = official - snap - closed
    print(f"{r['quarter']}: snapshot {snap:,} + closed {closed:,} = {snap + closed:,} vs official {official:,} ({gap:+.3%})")
    if abs(gap) > TOLERANCE and KNOWN_GAPS.get(r["quarter"]) != short:
        bad.append(r["quarter"])
    elif KNOWN_GAPS.get(r["quarter"]) == short:
        print(f"  known gap of {short} accepted (DECISIONS, 2 Nov)")
sys.exit(f"FAIL: {bad}" if bad else 0)
