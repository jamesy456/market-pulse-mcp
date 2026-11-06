"""Openings against closures (batch C, 5 Nov 2026) against exact counts.

Run: .venv/bin/python scripts/check_closures.py   (prints totals only, never a single small count)
1. registrations_against_closures, 35 industry selections x the UK, every region and nation, Leeds and 40 councils x
   three periods: does each likely range hold the exact count, and does any 'clear' verdict point the wrong way?
2. Batches: on exact counts, how often does the side with more flip when a year's window moves on by one quarter, and
   for a single quarter? This is why under a year gets no verdict, and how far a one-year verdict can be trusted.
3. Fairness: what closures hold that registrations don't (ages, no SIC, unmatched, agents' addresses, postcodes with
   many closures that aren't flagged as agents, Companies House's default address).
4. Across the whole period: closed cells <= closures cells + October, which nothing publishes. Tighter links, within a
   year of registering, are checked at build time by build_levels.links.
"""
import random
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import server  # noqa: E402

INDUSTRIES = ([["10"], ["41"], ["43"], ["45"], ["47"], ["49"], ["56"], ["62"], ["68"], ["70"], ["86"], ["96"]]
              + [["471"], ["561"], ["620"], ["682"], ["702"], ["812"], ["960"], ["412"]]
              + [["47910"], ["56101"], ["62012"], ["68209"], ["70229"], ["81210"], ["96020"], ["49410"]]
              + [["ai-and-data"], ["cafes-and-coffee-shops"], ["beauty-and-wellbeing"], ["all"]]  # as check_largest.py
              + [["56101", "56102"], ["47910", "62012", "81210"], ["01110", "96020"]])
LEEDS = "E08000035"
LATEST = 2026 * 4 + 3
PERIODS = [(None, None), ("2025-Q1", "2025-Q4"), ("2022-Q1", "2022-Q4")]
raw = duckdb.connect(str(ROOT / "data/grid.duckdb"), read_only=True)
random.seed(20261105)
councils = random.sample([c for c, in server.db().execute(
    "SELECT ladcd FROM areas WHERE NOT northern_ireland AND ladcd <> 'unmatched' ORDER BY 1").fetchall()], 40)
regions = [r for r, in server.db().execute("SELECT DISTINCT rgncd FROM regions ORDER BY 1").fetchall()]
PLACES = ["UK", *regions, LEEDS, *councils]


def exact(codes: list[str], place: str, lo: int, hi: int) -> tuple[int, int]:
    """Exact (registered, dissolved): every company in the UK, or agents' addresses and Northern Ireland left out."""
    where = "" if place == "UK" else "AND NOT mass_postcode AND NOT northern_ireland AND ladcd IN (SELECT unnest($areas))"
    args = {"codes": codes, "lo": lo, "hi": hi} | ({} if place == "UK" else {"areas": list(server.members(place))})

    def total(t: str) -> int:  # fixed names
        return raw.execute(f"SELECT coalesce(sum(companies), 0) FROM {t} WHERE sic IN (SELECT unnest($codes)) "
                           f"AND year * 4 + quarter BETWEEN $lo AND $hi {where}", args).fetchone()[0]
    return total("grid") + total("grid_closed"), total("grid_gone")


ranges = blank = wrong = clear = none = few = rows = depends = 0
for ind in INDUSTRIES:
    sics = server.expand_sics(ind)[0]
    for place in PLACES:
        for frm, to in PERIODS:
            r = server.registrations_against_closures(ind, place, to, frm)
            lo, hi = server.period(frm, to, server.date.fromisoformat(server.meta()["snapshot_date"]))
            reg, gone = exact(sics, place, lo, hi)
            for row, t in zip(r.rows, (reg, gone)):
                rows += 1
                # no range means shown as under 10; a real count of 10 or more there is printed, not skipped
                blank += row["range"] is None and t >= 10
                ranges += bool(row["range"]) and not row["range"][0] <= t <= row["range"][1]
            if "More were likely registered" in r.summary:
                clear += 1
                wrong += reg <= gone
            elif "More were likely dissolved" in r.summary:
                clear += 1
                wrong += gone <= reg
            elif "Too few" in r.summary:
                few += 1
            elif "depends on the formation-agent" in r.summary:
                depends += 1
            else:
                none += 1
print(f"1. {rows:,} figures: {ranges:,} outside their likely range; {blank:,} of 10+ shown as under 10; {clear:,} clear verdicts, {wrong:,} the wrong way; "
      f"{depends:,} depending on the addresses left out; {none:,} no clear answer; {few:,} too few")



def by_quarter(codes: list[str], place: str) -> dict[int, list[int]]:
    """Exact [registered, dissolved] per quarter in the last two years; one query each, not one per window."""
    where = "" if place == "UK" else "AND NOT mass_postcode AND NOT northern_ireland AND ladcd IN (SELECT unnest($areas))"
    args = {"codes": codes, "lo": LATEST - 10} | ({} if place == "UK" else {"areas": list(server.members(place))})
    out = {q: [0, 0] for q in range(LATEST - 10, LATEST + 1)}
    for i, t in ((0, "grid"), (0, "grid_closed"), (1, "grid_gone")):
        for q, n in raw.execute(f"SELECT year * 4 + quarter, sum(companies) FROM {t} WHERE sic IN (SELECT unnest($codes)) "
                                f"AND year * 4 + quarter BETWEEN $lo AND {LATEST} {where} GROUP BY 1", args).fetchall():
            out[q][i] += n
    return out


def flipped(pairs_: list[tuple[int, int]]) -> tuple[int, int]:
    """(flips, comparisons) between neighbours only, both sides of both at least 50 and neither a tie."""
    side = [a > b if min(a, b) >= 50 and a != b else None for a, b in pairs_]
    both = [(x, y) for x, y in zip(side, side[1:]) if x is not None and y is not None]
    return sum(x != y for x, y in both), len(both)


flips = pairs = q_flips = q_pairs = clear_years = clear_flips = 0
for ind in INDUSTRIES:
    sics = server.expand_sics(ind)[0]
    for place in PLACES:
        q = by_quarter(sics, place)
        f, n = flipped([(sum(q[k][0] for k in range(e - 3, e + 1)), sum(q[k][1] for k in range(e - 3, e + 1)))
                        for e in range(LATEST - 7, LATEST + 1)])
        flips, pairs = flips + f, pairs + n
        ends = range(LATEST - 7, LATEST + 1)
        tests = [server.change(sum(q[k][1] for k in range(e - 3, e + 1)), sum(q[k][0] for k in range(e - 3, e + 1)))
                 for e in ends]
        for a, b in zip(tests, tests[1:]):
            clear_years += a.startswith("clear")
            clear_flips += a.startswith("clear") and b.startswith("clear") and a != b
        f, n = flipped([tuple(q[k]) for k in range(LATEST - 7, LATEST + 1)])
        q_flips, q_pairs = q_flips + f, q_pairs + n
print(f"2. side with more flips (both sides at least 50): {flips:,} of {pairs:,} moves of a year's window by one quarter; "
      f"{q_flips:,} of {q_pairs:,} from one quarter to the next; of {clear_years:,} clear years, {clear_flips:,} clear the other "
      "way a quarter later")

share = raw.execute("""SELECT round(100.0 * sum(companies) FILTER (WHERE mass_postcode) / sum(companies), 2),
                              round(100.0 * sum(companies) FILTER (WHERE ladcd = 'unmatched') / sum(companies), 2),
                              round(100.0 * sum(companies) FILTER (WHERE sic = 'none') / sum(companies), 2)
                       FROM grid_gone""").fetchone()
open_share = raw.execute("""SELECT round(100.0 * sum(companies) FILTER (WHERE mass_postcode) / sum(companies), 2),
                                   round(100.0 * sum(companies) FILTER (WHERE ladcd = 'unmatched') / sum(companies), 2),
                                   round(100.0 * sum(companies) FILTER (WHERE sic = 'none') / sum(companies), 2)
                            FROM (SELECT * FROM grid UNION ALL BY NAME SELECT * EXCLUDE age FROM grid_closed)""").fetchone()
print(f"3. share at agents' addresses, unmatched, no SIC: closures {share}, registrations {open_share}")
TIDY = "regexp_replace(upper(coalesce(postcode, '')), '[^A-Z0-9]', '', 'g')"
raw.execute(f"""CREATE TEMP TABLE pc AS SELECT {TIDY} AS pc, count(*) AS n
                FROM read_json('{ROOT}/data/closures/days/*.jsonl', format='newline_delimited',
                               columns={{postcode: 'VARCHAR'}}) WHERE {TIDY} <> '' GROUP BY 1""")
live = raw.execute(f"""SELECT count(*), sum(n) FROM pc WHERE n >= 500""").fetchone()
print(f"   postcodes with 500+ closures: {live[0]:,}, holding {live[1]:,} of "
      f"{raw.execute('SELECT sum(n) FROM pc').fetchone()[0]:,} closures")
csv = sorted((ROOT / "data/snapshots").glob("BasicCompanyDataAsOneFile-*.csv"))[-1]
raw.execute(f"""CREATE TEMP TABLE now AS SELECT regexp_replace(upper(coalesce("RegAddress.PostCode", '')), '[^A-Z0-9]', '', 'g')
                AS pc, count(*) AS n FROM read_csv('{csv}', header=true, all_varchar=true) GROUP BY 1""")
hidden = raw.execute("""SELECT count(*), coalesce(sum(p.n), 0) FROM pc p LEFT JOIN now USING (pc)
                        WHERE p.n >= 100 AND coalesce(now.n, 0) < 500""").fetchone()
print(f"   postcodes with 100+ closures not flagged as agents: {hidden[0]:,}, holding {hidden[1]:,} closures")
raw.execute(f"""CREATE TEMP TABLE d AS SELECT {TIDY} AS pc, CAST(date_of_cessation AS DATE) AS died
                FROM read_json('{ROOT}/data/closures/days/*.jsonl', format='newline_delimited',
                               columns={{postcode: 'VARCHAR', date_of_cessation: 'VARCHAR'}})""")
default = raw.execute("""SELECT count(*), count(*) FILTER (WHERE pc = 'CF148LH') FROM d
                         WHERE died >= DATE '2025-10-01'""").fetchone()
print(f"   latest year: {default[1] / default[0]:.1%} of closures at Companies House's default address (CF14 8LH), "
      f"flagged as agents: {raw.execute('SELECT coalesce(max(n), 0) >= 500 FROM now WHERE pc = ?', ['CF148LH']).fetchone()[0]}")
for t, name in (("grid_gone", "closures"), ("(SELECT * FROM grid UNION ALL BY NAME SELECT * EXCLUDE age FROM grid_closed)", "registrations")):
    print(f"   latest year, {name} at agents' addresses: " + "{:.1%}".format(raw.execute(
        f"SELECT sum(companies) FILTER (WHERE mass_postcode) / sum(companies) FROM {t} "
        f"WHERE year * 4 + quarter BETWEEN {LATEST - 3} AND {LATEST}").fetchone()[0]))
lookup = next((ROOT / "data/lookup").glob("PCD_OA21*.csv"))
shares = [r[0] for r in raw.execute(f"""WITH lk AS (SELECT regexp_replace(upper(pcds), '[^A-Z0-9]', '', 'g') AS pc, ladcd
                                                     FROM read_csv('{lookup}', all_varchar=true))
    SELECT count(*) FILTER (WHERE p.n >= 100) / count(*) FROM d JOIN lk USING (pc) JOIN pc p USING (pc)
    LEFT JOIN now USING (pc) WHERE coalesce(now.n, 0) < 500 AND d.died >= DATE '2025-10-01'
    GROUP BY ladcd HAVING count(*) >= 200 ORDER BY 1""").fetchall()]
print(f"   latest year, closures at a postcode with 100+ closures, by council (200+ closures): median "
      f"{shares[len(shares) // 2]:.0%}, {sum(x >= 0.2 for x in shares)} of {len(shares)} at 20% or more")

links = server.db().execute("""WITH c AS (SELECT ladcd, sic, sum(greatest(protected - 4, 0)) AS low FROM p_area_closed GROUP BY 1, 2),
    g AS (SELECT ladcd, sic, sum(protected + 4) AS high FROM p_area_gone GROUP BY 1, 2)
    SELECT count(*), count(*) FILTER (WHERE c.low = g.high), count(*) FILTER (WHERE c.low > g.high)
    FROM g JOIN c USING (ladcd, sic)""").fetchone()
print(f"4. council x code totals: {links[0]:,}; the closed cells' lowest total equals the closures' highest in {links[1]:,} "
      f"(would pin it if October held none, which nothing published shows) and passes it in {links[2]:,} (October closures)")
