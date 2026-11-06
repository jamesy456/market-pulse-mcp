"""Check the closures download against official dissolutions. Prints totals only, never a company.

Run: .venv/bin/python scripts/closures_check.py
Fails if any day from 2021-01-01 to 2026-09-30 is missing, doesn't pass the download's own day check, or a company
appears twice. Then, per quarter, companies dissolved on that date (the types the official 'All companies' line covers,
as closed_check.py) against official Dissolutions. An exact match isn't expected: a company dissolved then restored
counts officially but isn't dissolved now, so the download should fall short, by about the restorations since. That
gap is printed beside official restorations. Cross-checks by company number: every company in the earlier backfill
dissolved in the window should be here, and nothing here should be in the snapshot.
"""
import csv
import json
import sys
from datetime import timedelta
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backfill_closures import FIRST, LAST, MANIFEST, OUT, finished  # noqa: E402
from closed_check import TYPES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "data/official/incorporated_2026Q1_oldmethod.csv"  # quarterly, to Mar 2026
NEW = ROOT / "data/official/incorporated_2026Q3.csv"  # monthly, Apr-Sep 2026
SNAPSHOT = ROOT / "data/snapshots/BasicCompanyDataAsOneFile-2026-11-01.csv"
EARLIER = ROOT / "data/closed/days"
MONTHS = {"Apr": 2, "May": 2, "Jun": 2, "Jul": 3, "Aug": 3, "Sep": 3}


def small(n: int) -> str:
    return "under 10" if 0 < n < 10 else f"{n:,}"


def official() -> tuple[dict, dict]:
    """(dissolutions, restorations) per 'YYYY-Qn', UK, all companies."""
    gone, back = {}, {}
    for r in csv.DictReader(open(OLD)):
        if r["Region"] == "UK" and r["Corporate body type"] == "All companies":
            d, m, y = r["Date"].split("/")
            q = f"{y}-Q{(int(m) + 2) // 3}"
            if r["Attribute"] == "Dissolutions":
                gone[q] = int(r["Value"])
            elif r["Attribute"] == "Restorations":
                back[q] = int(r["Value"])
    for r in csv.DictReader(open(NEW, encoding="utf-8-sig")):
        if r["Geography"] == "UK" and r["Corporate Bodies"] == "All Companies":
            month, year = r["Period"].split("-")
            q = f"20{year}-Q{MONTHS[month]}"
            # 'Dissolution' (voluntary, compulsory, liquidation; there is no Total row), not 'Struck off': a company is
            # dissolved by Gazette notice about a week after strike-off, and that notice is the date_of_cessation.
            # The two agree for 2026-Q2 only because the release says all of that quarter's were dissolved by June.
            if r["Attribute"] == "Dissolution":
                gone[q] = gone.get(q, 0) + int(r["Value"])
            elif r["Attribute"] == "Restorations" and r["Route"] == "Total":
                back[q] = back.get(q, 0) + int(r["Value"])
    return gone, back


expected = {m["day"]: m["hits"] for m in map(json.loads, MANIFEST.read_text().splitlines())}
days = [FIRST + timedelta(n) for n in range((LAST - FIRST).days + 1)]
bad = [d for d in days if not finished(OUT / f"{d}.jsonl", d.isoformat(), expected.get(d.isoformat()))]
print(f"{len(days) - len(bad):,} of {len(days):,} days whole")
quiet = [d for d in days if expected.get(d.isoformat()) == 0 and d.weekday() < 5]
print(f"weekdays with no dissolutions: {len(quiet)}")
fail = bool(bad)
# Dissolutions are gazetted in Tuesday batches, so a lost strike-off day would be a Tuesday with nothing. Other weekdays
# are about 100 companies each, too few to matter. Christmas week 2021's Tuesday holds 125; the check is on none at all.
tuesdays = [d for d in days if d.weekday() == 1]
empty = [d for d in tuesdays if expected.get(d.isoformat()) == 0]
share = sum(expected[d.isoformat()] for d in tuesdays) / sum(expected.values())
print(f"on Tuesdays: {share:.1%} of dissolutions; empty Tuesdays: {len(empty)}")
fail |= bool(empty)

con = duckdb.connect()
con.execute(f"""CREATE TABLE gone AS SELECT upper(trim(company_number)) AS number, company_type,
        CAST(date_of_cessation AS DATE) AS died, CAST(date_of_creation AS DATE) AS born
    FROM read_json('{OUT}/*.jsonl', format='newline_delimited', columns={{company_number: 'VARCHAR',
        company_type: 'VARCHAR', date_of_creation: 'VARCHAR', date_of_cessation: 'VARCHAR'}})""")
total, unique = con.execute("SELECT count(*), count(DISTINCT number) FROM gone").fetchone()
print(f"{total:,} rows, {unique:,} companies")
fail |= total != unique
no_date = con.execute("SELECT count(*) FROM gone WHERE born IS NULL").fetchone()[0]
print(f"no incorporation date: {small(no_date)}")
print("types outside the official line:", ", ".join(f"{t or 'blank'} {small(n)}" for t, n in con.execute(
    "SELECT company_type, count(*) FROM gone WHERE company_type IS NULL OR company_type NOT IN (SELECT unnest($t)) "
    "GROUP BY 1 ORDER BY 2 DESC", {"t": TYPES}).fetchall()))

ours = dict(con.execute("""SELECT year(died) || '-Q' || quarter(died), count(*) FROM gone
    WHERE company_type IN (SELECT unnest($t)) GROUP BY 1""", {"t": TYPES}).fetchall())
gone, back = official()
quarters = sorted(ours)
for q in quarters:
    n, o = ours[q], gone.get(q)
    print(f"{q}: ours {n:,} official {o:,} short {o - n:,} ({(o - n) / o:+.2%}), official restorations {back.get(q, 0):,}"
          if o else f"{q}: ours {n:,}, no official figure")
known = [q for q in quarters if q in gone]
short = sum(gone[q] - ours[q] for q in known)
restored = sum(back.get(q, 0) for q in known)
print(f"all quarters: short {short:,} of {sum(gone[q] for q in known):,}; official restorations {restored:,}")
# Quarters before 2022-Q2 swing both ways (a batch either side of a quarter end, e.g. 4 Jan 2022 is double a normal
# week), so the test is on the whole period: short, by no more than the companies restored since.
fail |= not 0 <= short <= restored

window = (FIRST.isoformat(), LAST.isoformat())
miss = con.execute(f"""SELECT count(*) FROM read_json('{EARLIER}/*.jsonl', format='newline_delimited',
        columns={{company_number: 'VARCHAR', date_of_cessation: 'VARCHAR'}}) e
    WHERE date_of_cessation BETWEEN $a AND $b
      AND upper(trim(company_number)) NOT IN (SELECT number FROM gone)""", {"a": window[0], "b": window[1]}).fetchone()[0]
print(f"in the earlier backfill, dissolved in the window, missing here: {small(miss)}")
# build_levels.links ties closed cells to closures cells, which needs a company in both to sit in the same cell.
tidy = "regexp_replace(upper(coalesce({}, '')), '[^A-Z0-9]', '', 'g')"
keys = f"""SELECT upper(trim(company_number)) AS number, {tidy.format('postcode')} AS pc, coalesce(sic_codes[1], '') AS sic,
    company_type AS kind, date_of_cessation AS died FROM read_json('{{}}/*.jsonl', format='newline_delimited',
    columns={{{{company_number: 'VARCHAR', company_type: 'VARCHAR', date_of_cessation: 'VARCHAR', sic_codes: 'VARCHAR[]',
              postcode: 'VARCHAR'}}}})"""
held = con.execute(f"""SELECT count(*), count(*) FILTER (WHERE a.pc <> b.pc), count(*) FILTER (WHERE a.sic <> b.sic),
        count(*) FILTER (WHERE a.kind <> b.kind), count(*) FILTER (WHERE a.died <> b.died)
    FROM ({keys.format(EARLIER)}) a JOIN ({keys.format(OUT)}) b USING (number)""").fetchone()
print(f"in both downloads: {held[0]:,}; different postcode {small(held[1])}, first SIC {small(held[2])}, "
      f"type {small(held[3])}, dissolution date {small(held[4])}")
both = con.execute(f"""SELECT count(*) FROM gone WHERE number IN (
    SELECT upper(trim(CompanyNumber)) FROM read_csv('{SNAPSHOT}', all_varchar=true, header=true,
        normalize_names=false, ignore_errors=false))""").fetchone()[0]
print(f"also in the 1 Nov snapshot: {small(both)}")
sys.exit(1 if fail else 0)
