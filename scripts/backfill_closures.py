"""Batch C: every company dissolved since 2021, whatever year it was incorporated, by dissolution day, from the
Companies House advanced search API. backfill_closed.py can't answer this: it holds companies incorporated since 2021.

Run: .venv/bin/python -u scripts/backfill_closures.py   (resumable: finished days are skipped)
Writes data/closures/days/<day>.jsonl and data/closures/manifest.jsonl, all gitignored. The key is read from .env and
never printed. Strike-off days can pass the 5,000 page size, and the API doesn't state how deep paging goes, so a big day
is split by incorporation date until each part fits on one page, rather than paged. Parts must add up to the day's hits
exactly: a company with no incorporation date can't appear in a split day's parts, and hits can move mid-day. A day that
doesn't add up after 3 tries is not saved, the run carries on, and the end of the run names it (exit 1), so nothing
incomplete is ever marked finished; rerunning retries it. A row with the wrong dissolution day stops the run, as the filter
would then not be doing what we think. Finished days are checked again on resume. A bodiless 404 means no results (probed
2 Nov 2026, closed_check.py), so an empty day is asked twice; the quarterly match to official dissolutions (the check that
follows) is the end-to-end test.
"""
import base64
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backfill_closed import KEEP, PAGE, get  # noqa: E402
from closed_check import key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/closures/days"
MANIFEST = ROOT / "data/closures/manifest.jsonl"
FIRST, LAST = date(2021, 1, 1), date(2026, 9, 30)  # the last quarter both openings and official figures cover
OLDEST = date(1800, 1, 1)  # the widest incorporation dates a split day starts from


class Mismatch(Exception):
    """A day's counts don't add up; try the day again from a fresh probe."""


def part(auth: str, day: str, lo: date | None, hi: date | None) -> tuple[int, list[dict]]:
    """(hits, rows) for one dissolution day, between two incorporation dates if given, split until each part fits."""
    q = {"company_status": "dissolved", "dissolved_from": day, "dissolved_to": day}
    if lo:
        q |= {"incorporated_from": lo.isoformat(), "incorporated_to": hi.isoformat()}
    hits = int(get(auth, day, {**q, "size": 1, "start_index": 0}).get("hits", 0))
    if hits == 0 and lo is None:  # an empty day is asked twice, as a stray 404 would also read as empty
        hits = int(get(auth, day, {**q, "size": 1, "start_index": 0}).get("hits", 0))
    if hits == 0:
        return 0, []
    if hits <= PAGE:
        items = get(auth, day, {**q, "size": PAGE, "start_index": 0}).get("items", [])
        if len(items) != hits:
            raise Mismatch(f"hits {hits}, retrieved {len(items)}")
        return hits, items
    if lo is None:
        lo, hi = OLDEST, date.today()
    if lo == hi:
        raise Mismatch(f"{hits} companies share an incorporation day, too many to split")
    mid = lo + (hi - lo) // 2
    (n1, rows1), (n2, rows2) = part(auth, day, lo, mid), part(auth, day, mid + timedelta(days=1), hi)
    if n1 + n2 != hits:
        raise Mismatch(f"parts add up to {n1 + n2} of {hits}")
    return hits, rows1 + rows2


def day_rows(auth: str, day: str) -> list[dict]:
    """Every row for a day. Raises Mismatch if it still doesn't add up after 3 tries."""
    for attempt in range(3):
        try:
            hits, items = part(auth, day, None, None)
            numbers = {i.get("company_number") for i in items}
            if len(numbers) != hits or None in numbers or "" in numbers:
                raise Mismatch(f"{hits} hits but repeated or blank company numbers")
            break
        except Mismatch as e:
            print(f"{day}: {e}, try {attempt + 1} of 3", flush=True)
            if attempt == 2:
                raise
    for i in items:  # each row must carry the day it was asked for, or the filter isn't doing what we think
        if i.get("date_of_cessation") != day:
            raise SystemExit(f"{day}: a row has another or no dissolution date")
    # Company numbers and postcodes stay local (gitignored), like the snapshot CSV; only protected sums are served.
    return [{**{k: i.get(k) for k in KEEP},
             "postcode": (i.get("registered_office_address") or {}).get("postal_code")} for i in items]


def finished(f: Path, day: str, hits: int | None) -> bool:
    """Is this day's file whole: its manifest count of unique, non-blank numbers, all dissolved on that day?"""
    if hits is None or not f.exists():
        return False
    rows = [json.loads(line) for line in f.read_text().splitlines()]
    numbers = {r.get("company_number") for r in rows}
    return (len(rows) == len(numbers) == hits and None not in numbers and "" not in numbers
            and all(r.get("date_of_cessation") == day for r in rows))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    auth = base64.b64encode(f"{key()}:".encode()).decode()
    expected = {}  # day -> hits, from the manifest
    if MANIFEST.exists():
        expected = {m["day"]: m["hits"] for m in map(json.loads, MANIFEST.read_text().splitlines())}
    d, done, kept, failed, t0 = FIRST, 0, 0, [], time.time()
    while d <= LAST:
        f = OUT / f"{d}.jsonl"
        if not finished(f, d.isoformat(), expected.get(d.isoformat())):
            try:
                rows = day_rows(auth, d.isoformat())
            except Mismatch as e:
                failed.append(f"{d} ({e})")
                d += timedelta(days=1)
                continue
            tmp = f.with_suffix(".part")
            tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
            os.replace(tmp, f)  # a day file exists only once it is complete
            with open(MANIFEST, "a") as m:
                m.write(json.dumps({"day": d.isoformat(), "hits": len(rows)}) + "\n")
            done, kept = done + 1, kept + len(rows)
            if done % 50 == 0:
                print(f"{d}: {done} days fetched, {kept:,} companies, {time.time() - t0:.0f}s", flush=True)
        d += timedelta(days=1)
    print(f"finished: {done} new days, {kept:,} companies, {len(failed)} days incomplete", flush=True)
    if failed:
        raise SystemExit("incomplete, not saved; rerun to retry: " + "; ".join(failed))


if __name__ == "__main__":
    main()
