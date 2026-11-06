# Hour 1-3 spike: can the snapshot load, how long, how many rows, which categories.
import sys, time, duckdb
csv = sys.argv[1]
con = duckdb.connect("data/spike.duckdb")
t = time.time()
con.execute(f"""
CREATE OR REPLACE TABLE raw AS
SELECT trim("CompanyNumber") AS company_number,
       "CompanyCategory" AS category,
       "CompanyStatus" AS status,
       "IncorporationDate" AS inc_date_text,
       "RegAddress.PostCode" AS postcode,
       "SICCode.SicText_1" AS sic1
FROM read_csv('{csv}', all_varchar=true, header=true, normalize_names=false)
""")
print(f"load secs: {time.time()-t:.1f}")
print("rows:", con.execute("select count(*) from raw").fetchone()[0])
print("categories:")
for r in con.execute("select category, count(*) n from raw group by 1 order by 2 desc").fetchall(): print("  ", r)
print("statuses:")
for r in con.execute("select status, count(*) from raw group by 1 order by 2 desc limit 12").fetchall(): print("  ", r)
print("date sample:", con.execute("select inc_date_text from raw limit 3").fetchall())
print("unparseable dates:", con.execute("select count(*) from raw where try_strptime(inc_date_text,'%d/%m/%Y') is null").fetchone()[0])
