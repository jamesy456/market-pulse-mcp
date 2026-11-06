"""Build the summary grid: local authority x primary SIC x quarter x company type.

Run: .venv/bin/python scripts/build_grid.py
Writes data/grid.duckdb (tables: grid, grid_closed, meta, protected p_* tables), then data/serve.duckdb with only
the protected tables and lookups (scripts/export_serving.py). The MCP server opens serve.duckdb read-only.
Only codes, dates and counts are kept: no company names, numbers or address lines.
Closed companies (phase B) come from data/closed/days/*.jsonl (scripts/backfill_closed.py, checked by
scripts/backfill_check.py) and get their own protected tables; the live tables are built exactly as before.
Closures (batch C) come from data/closures/days/*.jsonl (scripts/backfill_closures.py, checked by
scripts/closures_check.py): every company dissolved since 2021, by dissolution quarter, in the _gone tables.
"""
import hashlib
from datetime import date
from pathlib import Path

import duckdb

import build_levels
import export_serving
import pin_check

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data/snapshots/BasicCompanyDataAsOneFile-2026-11-01.csv"
CLOSED = ROOT / "data/closed/days"
CLOSURES = ROOT / "data/closures/days"
LOOKUP = ROOT / "data/lookup/PCD_OA21_LSOA21_MSOA21_LAD_AUG26_UK_LU.csv"
OUT = ROOT / "data/grid.duckdb"
SNAPSHOT_DATE = date(2026, 11, 1)
SNAPSHOT_SHA256 = "c3bcf0942a58bd1a6a9ed8829119befd564fbc79d3ace1d5382276e3e05b8ed1"
MASS_CUTOFF = 500  # James's pick, 1 Nov 2026 (DECISIONS.md)
FROM_YEAR = 2021


cell_key_salt = build_levels.cell_key_salt

# SPEC counting rules: the tools cover private limited (shares and guarantee), PLC and LLP.
TYPE_GROUPS = """CASE CompanyCategory
    WHEN 'Private Limited Company' THEN 'private_limited'
    WHEN 'PRI/LTD BY GUAR/NSC (Private, limited by guarantee, no share capital)' THEN 'private_limited'
    WHEN 'PRI/LBG/NSC (Private, Limited by guarantee, no share capital, use of ''Limited'' exemption)' THEN 'private_limited'
    WHEN 'Public Limited Company' THEN 'plc'
    WHEN 'Limited Liability Partnership' THEN 'llp' END"""

# Postcode tidy: ' ls1  4ap ' -> 'LS14AP'. Same expression on both sides of the join.
TIDY = "regexp_replace(upper(coalesce({}, '')), '[^A-Z0-9]', '', 'g')"

# Northern Ireland is read from the company's own postcode. The lookup's NI rows are never loaded, as their licence is
# internal business use only (README), so no NI council is known and those companies share one code.
NI = "regexp_matches(pc, '^BT[0-9]')"
UNMATCHED = "lk.ladcd IS NULL OR lk.ladcd LIKE '_99999999'"
PLACE = f"""CASE WHEN {NI} THEN 'N92000002' WHEN {UNMATCHED} THEN 'unmatched' ELSE lk.ladcd END AS ladcd,
        CASE WHEN {NI} THEN 'Northern Ireland' WHEN {UNMATCHED} THEN 'Unmatched postcode' ELSE lk.ladnm END AS ladnm,
        {NI} AS northern_ireland"""

sha = hashlib.sha256()
with open(SNAPSHOT, "rb") as f:
    for block in iter(lambda: f.read(1 << 24), b""):
        sha.update(block)
# SC-12: the cell key has no snapshot term, so answers from two snapshots would show the same rounding step.
if sha.hexdigest() != SNAPSHOT_SHA256:
    raise SystemExit("Add the two-snapshot rounding check before building a new snapshot (AUDIT-FINDINGS.md, SC-12)")

OUT.unlink(missing_ok=True)
con = duckdb.connect(str(OUT))
con.execute(f"""CREATE TEMP TABLE lk AS SELECT {TIDY.format('pcds')} AS pc, ladcd, ladnm
                FROM read_csv('{LOOKUP}', all_varchar=true) WHERE pcds NOT LIKE 'BT%'""")
if con.execute("SELECT count(*) FROM lk WHERE pc LIKE 'BT%' OR ladcd LIKE 'N%'").fetchone()[0]:
    raise SystemExit("Northern Ireland rows reached the lookup; their licence is internal business use only")
con.execute(f"""CREATE TEMP TABLE c AS SELECT
        upper(trim(CompanyNumber)) AS number,
        {TIDY.format('"RegAddress.PostCode"')} AS pc,
        strptime(IncorporationDate, '%d/%m/%Y') AS d,
        {TYPE_GROUPS} AS type_group,
        CASE WHEN "SICCode.SicText_1" IS NULL OR "SICCode.SicText_1" = 'None Supplied'
               OR left("SICCode.SicText_1", 5) = '99999' THEN 'none'
             ELSE left("SICCode.SicText_1", 5) END AS sic
    FROM read_csv('{SNAPSHOT}', all_varchar=true)""")
# Mass flag counts every company at the postcode (all types, all years), as the cut-off was chosen on that basis.
con.execute("CREATE TEMP TABLE pcount AS SELECT pc, count(*) AS n FROM c WHERE pc <> '' GROUP BY pc")
con.execute(f"""CREATE TABLE grid AS SELECT
        {PLACE},
        c.sic, c.type_group,
        year(c.d) AS year, quarter(c.d) AS quarter,
        coalesce(pcount.n >= {MASS_CUTOFF}, false) AS mass_postcode,
        count(*)::INTEGER AS companies
    FROM c LEFT JOIN lk USING (pc) LEFT JOIN pcount USING (pc)
    WHERE c.type_group IS NOT NULL AND year(c.d) >= {FROM_YEAR}
    GROUP BY ALL""")
# Batch B: companies registered before 2021 (or with no date) still live in the snapshot, so "how many are live now"
# is these plus every quarter since. A live-now table overlapping the quarterly ones pinned 21 small counts (a live-now
# cell shown 0 over four quarters shown 5 forces each to 1); these are different companies, so nothing ties them.
con.execute(f"""CREATE TABLE grid_pre2021 AS SELECT
        {PLACE},
        c.sic, c.type_group,
        coalesce(pcount.n >= {MASS_CUTOFF}, false) AS mass_postcode,
        count(*)::INTEGER AS companies
    FROM c LEFT JOIN lk USING (pc) LEFT JOIN pcount USING (pc)
    WHERE c.type_group IS NOT NULL AND (c.d IS NULL OR year(c.d) < {FROM_YEAR})
    GROUP BY ALL""")
# Closed companies, mapped to the snapshot's categories: CICs are their own snapshot category (left out above), so
# the API's community-interest-company subtype is left out too; unlimited companies aren't counted either.
CLOSED_ROWS = """CREATE TEMP TABLE {name} AS SELECT upper(trim(company_number)) AS number,
        {pc} AS pc,
        CAST(date_of_creation AS DATE) AS d, CAST(date_of_cessation AS DATE) AS died,
        CASE WHEN company_subtype = 'community-interest-company' THEN NULL
             WHEN company_type IN ('ltd', 'private-limited-guarant-nsc', 'private-limited-guarant-nsc-limited-exemption')
               THEN 'private_limited'
             WHEN company_type = 'plc' THEN 'plc'
             WHEN company_type = 'llp' THEN 'llp' END AS type_group,
        CASE WHEN len(coalesce(sic_codes, [])) = 0 OR left(sic_codes[1], 5) = '99999' THEN 'none'
             ELSE left(sic_codes[1], 5) END AS sic
    FROM read_json('{path}/*.jsonl', format='newline_delimited',
        columns={{company_number: 'VARCHAR', company_type: 'VARCHAR', company_subtype: 'VARCHAR',
                 date_of_creation: 'VARCHAR', date_of_cessation: 'VARCHAR', sic_codes: 'VARCHAR[]', postcode: 'VARCHAR'}})"""
con.execute(CLOSED_ROWS.format(name="cl", pc=TIDY.format("postcode"), path=CLOSED))
overlap = con.execute("SELECT count(*) FROM cl WHERE EXISTS (SELECT 1 FROM c WHERE c.number = cl.number)").fetchone()[0]
if overlap:  # backfill_check found 0; a new snapshot or backfill must be re-checked, not silently deduped
    raise SystemExit(f"{overlap:,} closed companies are also in the snapshot; rerun scripts/backfill_check.py")
# Same postcode lookup and the same mass flag (live companies per postcode, as the cut-off was chosen on that).
# age: closed within a year of incorporation or later, so 1-year survival can be read from a clean partition.
# Pseudo codes (Isle of Man, Channel Islands: '?99999999') never occur among live companies; they count as unmatched.
con.execute(f"""CREATE TABLE grid_closed AS SELECT
        {PLACE},
        cl.sic, cl.type_group,
        year(cl.d) AS year, quarter(cl.d) AS quarter,
        CASE WHEN cl.died < cl.d + INTERVAL 1 YEAR THEN 'under_1y' ELSE '1y_plus' END AS age,
        coalesce(pcount.n >= {MASS_CUTOFF}, false) AS mass_postcode,
        count(*)::INTEGER AS companies
    FROM cl LEFT JOIN lk USING (pc) LEFT JOIN pcount USING (pc)
    WHERE cl.type_group IS NOT NULL AND year(cl.d) >= {FROM_YEAR}
    GROUP BY ALL""")
# Batch C: every company dissolved in the window, whatever year it was incorporated, by the quarter it was dissolved.
# Same types, lookup and mass flag as the tables above, so closures compare with registrations. Nothing here may be in
# the snapshot (closures_check.py found 0).
con.execute(CLOSED_ROWS.format(name="gone", pc=TIDY.format("postcode"), path=CLOSURES))
overlap = con.execute("SELECT count(*) FROM gone WHERE EXISTS (SELECT 1 FROM c WHERE c.number = gone.number)").fetchone()[0]
if overlap:
    raise SystemExit(f"{overlap:,} dissolved companies are also in the snapshot; rerun scripts/closures_check.py")
con.execute(f"""CREATE TABLE grid_gone AS SELECT
        {PLACE},
        g.sic, g.type_group,
        year(g.died) AS year, quarter(g.died) AS quarter,
        coalesce(pcount.n >= {MASS_CUTOFF}, false) AS mass_postcode,
        count(*)::INTEGER AS companies
    FROM gone g LEFT JOIN lk USING (pc) LEFT JOIN pcount USING (pc)
    WHERE g.type_group IS NOT NULL
    GROUP BY ALL""")
# SIC descriptions come from the snapshot's own "81210 - General cleaning of buildings" text (all 4 SIC columns).
con.execute(f"""CREATE TABLE sic AS SELECT DISTINCT left(t, 5) AS code, trim(substr(t, 9)) AS description
    FROM (SELECT unnest(["SICCode.SicText_1", "SICCode.SicText_2", "SICCode.SicText_3", "SICCode.SicText_4"]) AS t
          FROM read_csv('{SNAPSHOT}', all_varchar=true))
    WHERE regexp_matches(t, '^[0-9]{{5}} - ') AND left(t, 5) <> '99999'""")
# Batch B check_levels.py: about 0.6% of companies registered before 2021 still carry a SIC 2003 code, which isn't in
# this list and doesn't mean the same (2003's 51 was wholesale, 2007's is air transport). They are left out of the
# before-2021 table, and live-now answers say how many (rounded to 100: a GB-wide total, never a small count).
old_sic = con.execute("""SELECT coalesce(sum(companies), 0) FROM grid_pre2021
                         WHERE sic <> 'none' AND sic NOT IN (SELECT code FROM sic)""").fetchone()[0]
con.execute("DELETE FROM grid_pre2021 WHERE sic <> 'none' AND sic NOT IN (SELECT code FROM sic)")
print(f"before 2021: {old_sic:,} companies with an old (2003) SIC code left out")
gone_old_sic = con.execute("""SELECT coalesce(sum(companies), 0) FROM grid_gone
                              WHERE sic <> 'none' AND sic NOT IN (SELECT code FROM sic)""").fetchone()[0]
con.execute("DELETE FROM grid_gone WHERE sic <> 'none' AND sic NOT IN (SELECT code FROM sic)")
print(f"closures: {gone_old_sic:,} companies with an old (2003) SIC code left out")
# Cell-key protection (reviews 3 and 4). Each published cell is randomly rounded to a multiple of 5, once, at
# build time: up with probability (count mod 5) / 5, so totals stay unbiased. The direction comes from a salted
# hash of the table and cell key, so it is fixed and can't be predicted without the salt. Cells are protected
# at the grain the tools ask for, so a UK answer for one SIC and one quarter reads 1 cell, not ~86 tiny ones.
# The server reads only these p_* tables and `areas` (copied to serve.duckdb); `grid` (raw counts) stays for hand checks.
PROTECTED = {
    "p_uk": ("sic, year, quarter", "TRUE"),  # UK totals: all areas, NI and mass postcodes included
    "p_area": ("ladcd, sic, year, quarter", "NOT mass_postcode AND NOT northern_ireland"),  # GB areas + unmatched
    "p_mass": ("ladcd, sic, year, quarter", "mass_postcode AND NOT northern_ireland"),  # for the 'left out' count
}
# Closed tables: same structure, one more key column (age), so each is still a partition of the UK total.
PROTECTED_CLOSED = {f"{t}_closed": (f"{k}, age", w) for t, (k, w) in PROTECTED.items()}
PROTECTED_GONE = {f"{t}_gone": v for t, v in PROTECTED.items()}  # batch C: the quarter here is the dissolution quarter
salt = cell_key_salt()
for source, tables in (("grid", PROTECTED), ("grid_closed", PROTECTED_CLOSED), ("grid_gone", PROTECTED_GONE)):
    for table, (key, where) in tables.items():
        con.execute(f"""CREATE TABLE {table} AS SELECT {key},
                (n - n % 5 + CASE WHEN md5_number(concat_ws('|', ?, '{table}', {key})) % 5 < n % 5 THEN 5 ELSE 0 END)::INTEGER
                AS protected
            FROM (SELECT {key}, sum(companies)::INTEGER AS n FROM {source} WHERE {where} GROUP BY ALL)""", [salt])
# Pin repair (closed tables only): if a UK closed cell would pin a small area cell, it is replaced by the sum of its
# protected parts (area + mass + the NI remainder rounded as one cell), so that UK value adds no constraint. This is
# targeted, not a re-draw: re-rolling the salt until the check passes would make the published draw data-dependent.
repairs = {}
for suffix, extra, source in (("_closed", ", age", "grid_closed"), ("_gone", "", "grid_gone")):
    pinned, _ = pin_check.check(con, suffix, extra)
    repair = sorted({k[0] if k[-1] == "uk" else k for k, *_ in pinned})  # UK entries are keyed (key, "uk")
    cols = ["sic", "year", "quarter"] + (["age"] if extra else [])
    match = " AND ".join(f"{c} = ${i + 1}" for i, c in enumerate(cols))
    nth = len(cols) + 1
    for key in repair:
        keyed = ", ".join(f"${i + 1}" for i in range(len(cols)))
        con.execute(f"""UPDATE p_uk{suffix} SET protected = (
            SELECT coalesce(sum(protected), 0) FROM (SELECT protected FROM p_area{suffix} WHERE {match}
                                       UNION ALL SELECT protected FROM p_mass{suffix} WHERE {match}))
            + (SELECT coalesce(max(n - n % 5 + CASE WHEN md5_number(concat_ws('|', ${nth}, 'p_ni{suffix}', {keyed})) % 5 < n % 5
                                             THEN 5 ELSE 0 END), 0)
               FROM (SELECT sum(companies)::INTEGER AS n FROM {source} WHERE northern_ireland AND {match}))
            WHERE {match}""", [*key, salt])
    repairs[suffix] = len(repair)
    print(f"pin repair: {len(repair)} UK{suffix} cells replaced by the sum of their protected parts")
for suffix, extra in (("", ""), ("_closed", ", age"), ("_gone", "")):
    pinned, narrowed = pin_check.check(con, suffix, extra)  # review 5, F1: combining tables must not pin a small count
    if pinned:
        con.close()
        OUT.unlink()
        raise SystemExit(f"pin check FAILED (p_*{suffix}): {len(pinned)} cells below 10 can be pinned")  # no values in logs
    print(f"pin check p_*{suffix}: 0 cells pinned; {len(narrowed)} small cells narrowed but not pinned (accepted)")
con.execute("CREATE TABLE areas AS SELECT DISTINCT ladcd, ladnm, northern_ireland FROM grid")
unmatched = con.execute("SELECT 100.0 * sum(companies) FILTER (WHERE ladcd = 'unmatched') / sum(companies) FROM grid").fetchone()[0]
build_levels.build_regions(con)
build_levels.build_tables(con, salt)
build_levels.check(con)  # fails the build if any count below 10 can be pinned
con.execute("CREATE TABLE meta (key VARCHAR, value VARCHAR)")
con.executemany("INSERT INTO meta VALUES (?, ?)", [
    ("snapshot_date", SNAPSHOT_DATE.isoformat()), ("snapshot_sha256", sha.hexdigest()),
    ("lookup", LOOKUP.name), ("mass_cutoff", str(MASS_CUTOFF)), ("from_year", str(FROM_YEAR)),
    ("unmatched_pct", f"{unmatched:.2f}"), ("closed_pin_repairs", str(repairs["_closed"])),
    ("gone_pin_repairs", str(repairs["_gone"])), ("gone_old_sic", str(round(gone_old_sic, -2))),
    ("pre2021_old_sic", str(round(old_sic, -2))),
])
print(con.sql("SELECT count(*) cells, sum(companies) companies, count(DISTINCT ladcd) areas, count(DISTINCT sic) sics FROM grid"))
print(con.sql("""SELECT count(*) cells, sum(companies) companies, count(DISTINCT ladcd) areas,
    100.0 * sum(companies) FILTER (WHERE ladcd = 'unmatched') / sum(companies) AS unmatched_pct,
    count(DISTINCT ladcd) FILTER (WHERE ladcd NOT IN (SELECT ladcd FROM areas)) AS areas_not_in_live FROM grid_closed"""))
print(con.sql("SELECT * FROM meta"))
print(con.sql("SELECT count(*) sic_codes FROM sic"), con.sql("SELECT * FROM sic WHERE code = '81210'"))
con.close()
export_serving.export(OUT)
