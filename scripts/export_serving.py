"""Write data/serve.duckdb: only the protected tables and lookups the server reads (Codex review: never ship the raw grid).

Run: .venv/bin/python scripts/export_serving.py   (build_grid.py also runs it at the end)
data/grid.duckdb keeps the raw `grid` and `grid_closed` counts for hand checks and tests; it is never served or shared.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
SERVED = ["p_uk", "p_area", "p_mass", "p_uk_closed", "p_area_closed", "p_mass_closed", "areas", "sic", "meta", "regions",
          "p_agg", "p_agg_closed", "p_pre2021", "p_pre2021_mass",  # batch B: totals rounded once; before 2021, for live now
          "p_uk_gone", "p_area_gone", "p_mass_gone", "p_agg_gone"]  # batch C: closures by dissolution quarter


def export(grid: Path = ROOT / "data/grid.duckdb", out: Path = ROOT / "data/serve.duckdb") -> None:
    tmp = out.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute(f"ATTACH '{grid}' AS raw (READ_ONLY)")
    for t in SERVED:
        con.execute(f"CREATE TABLE {t} AS SELECT * FROM raw.{t}")
    # Regions (built by build_levels.py from the ONS lookup, Wales and Scotland as wholes): every GB council area once.
    gb = con.execute("""SELECT count(*), count(DISTINCT ladcd) FROM regions
                        WHERE ladcd IN (SELECT ladcd FROM raw.areas WHERE NOT northern_ireland)""").fetchone()
    n_gb = con.execute("SELECT count(*) FROM raw.areas WHERE NOT northern_ireland AND ladcd <> 'unmatched'").fetchone()[0]
    if gb != (n_gb, n_gb) or con.execute("SELECT count(*) FROM regions").fetchone()[0] != n_gb:
        con.close()
        tmp.unlink()
        raise SystemExit(f"export FAILED: regions cover {gb} of {n_gb} GB council areas, each exactly once")
    con.execute("DETACH raw")
    got = sorted(r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall())
    con.close()
    if got != sorted(SERVED):
        tmp.unlink()
        raise SystemExit(f"export FAILED: serving tables {got} != {sorted(SERVED)}")
    tmp.replace(out)  # replaced whole, so the server never sees a half-written file
    print(f"serving database written: {out.name}, tables {', '.join(SERVED)}")


if __name__ == "__main__":
    export()
