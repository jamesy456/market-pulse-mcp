"""Runs sql/first_count.sql against the 200-row test file (default)
or the real snapshot (--real) and checks it against the hand-worked answers.
Usage: .venv/bin/python scripts/check_query.py [--real]"""
import json, pathlib, sys, time, duckdb

root = pathlib.Path(__file__).resolve().parent.parent
real = '--real' in sys.argv
src = root / ('data/snapshots/BasicCompanyDataAsOneFile-2026-11-01.csv' if real else 'tests/fixtures/snapshot_sample.csv')

con = duckdb.connect()
con.execute(f"""
CREATE TABLE companies AS
SELECT trim("CompanyNumber") AS company_number, "CompanyCategory" AS category,
       "CompanyStatus" AS status, "IncorporationDate" AS inc_date_text,
       "RegAddress.PostCode" AS postcode, "SICCode.SicText_1" AS sic1
FROM read_csv(?, all_varchar=true, header=true)
""".replace('?', f"'{src}'"))

t = time.time()
try:
    rows = con.execute((root / 'sql/first_count.sql').read_text()).fetchall()
    cols = [d[0] for d in con.description]
except duckdb.Error as e:
    sys.exit(f'Your query failed: {e}')
print(f'query ran in {time.time() - t:.2f}s, {len(rows)} rows')
need = ['year', 'quarter', 'category', 'companies']
if cols[:4] != need:
    sys.exit(f'Columns should be {need}, got {cols}')

got = {(int(y), int(q), c): int(n) for y, q, c, n, *_ in rows}
PL, LLP = 'Private Limited Company', 'Limited Liability Partnership'
if real:
    for (y, q, c), n in sorted(got.items()):
        if y == 2026 and q == 3 and n >= 100: print(f'  2026 Q3  {c:<70} {n:>8,}')
    sys.exit(0)

exp = json.loads((root / 'tests/fixtures/expected.json').read_text())
checks = {
    'Q3 2026 private limited': (got.get((2026, 3, PL)), exp['q3_2026_private_limited']),
    'Q2 2026 private limited (30/06 edge)': (got.get((2026, 2, PL)), exp['q2_2026_private_limited']),
    'Q4 2026 private limited (01/10 edge)': (got.get((2026, 4, PL)), exp['q4_2026_private_limited']),
    'Q1 2021 private limited': (got.get((2021, 1, PL)), exp['q1_2021_private_limited']),
    'Q3 2026 LLP': (got.get((2026, 3, LLP)), exp['q3_2026_llp']),
    'all rows counted once': (sum(got.values()), exp['total_rows']),
}
ok = True
for name, (g, e) in checks.items():
    mark = 'PASS' if g == e else 'FAIL'
    ok &= g == e
    print(f'  {mark}  {name}: got {g}, expected {e}')
print('All checks pass. Try --real next.' if ok else 'Not yet. Read the FAIL lines.')
