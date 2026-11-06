"""Phase B backfill: every company incorporated since 2021 that has since been dissolved, from the Companies House
advanced search API. One request per incorporation day (about 1,000-1,500 hits, under the 5,000 page size).

Run: .venv/bin/python scripts/backfill_closed.py   (resumable: finished days are skipped)
Writes data/closed/days/<day>.jsonl (every type, unfiltered) and data/closed/manifest.jsonl (day, hits), all
gitignored. Each day must retrieve exactly its hit count, with no duplicate company numbers and a valid cessation
date on every row, or the run stops. Type filtering happens in the check and the build, so nothing is dropped here. The gate (closed_check.py) showed "dissolved" is the only closed status.
Companies dissolved on or after the snapshot date are also in the snapshot; build_grid drops them (cessation date kept).
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from closed_check import API, key  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/closed/days"
MANIFEST = ROOT / "data/closed/manifest.jsonl"
FIRST, LAST = date(2021, 1, 1), date(2026, 10, 31)
PAGE = 5000
PACE = 0.55  # 600 requests per 5 minutes is 0.5 s each; a little slower to be safe
KEEP = ("company_number", "company_type", "company_subtype", "date_of_creation", "date_of_cessation", "sic_codes")


def fetch(auth: str, day: str, start: int) -> dict:
    return get(auth, day, {"company_status": "dissolved", "incorporated_from": day, "incorporated_to": day,
                           "size": PAGE, "start_index": start})


def get(auth: str, day: str, params: dict) -> dict:
    """One advanced search request, paced, retrying 429s and server errors. Shared with backfill_closures.py."""
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        time.sleep(PACE)
        try:
            # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"}),
                                        timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404 and not e.read():
                return {"hits": 0, "items": []}
            if e.code == 429 or e.code >= 500:
                wait = 60 if e.code == 429 else 10 * 2 ** attempt
                print(f"{day}: HTTP {e.code}, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"{day}: {e}, retrying", flush=True)
            time.sleep(10 * 2 ** attempt)
    raise SystemExit(f"{day}: gave up after 6 attempts")


def day_rows(auth: str, day: str) -> list[dict]:
    first = fetch(auth, day, 0)
    hits, items = int(first.get("hits", 0)), list(first.get("items", []))
    while len(items) < hits:
        more = fetch(auth, day, len(items)).get("items", [])
        if not more:
            break
        items += more
    numbers = {i["company_number"] for i in items}
    if len(items) != hits or len(numbers) != hits:  # Codex review: retrieved must equal hits, no duplicates
        raise SystemExit(f"{day}: hits {hits}, retrieved {len(items)}, unique {len(numbers)}")
    for i in items:  # Codex review: a dissolved company without a valid cessation date stops the run
        date.fromisoformat(i.get("date_of_cessation") or "missing")
    # Company numbers and postcodes stay local (gitignored), like the snapshot CSV; only protected sums are served.
    return [{**{k: i.get(k) for k in KEEP},
             "postcode": (i.get("registered_office_address") or {}).get("postal_code")} for i in items]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    auth = base64.b64encode(f"{key()}:".encode()).decode()
    finished = {}  # day -> hits, from the manifest; a day is skipped only if its file has exactly that many rows
    if MANIFEST.exists():
        finished = {m["day"]: m["hits"] for m in map(json.loads, MANIFEST.read_text().splitlines())}
    d, done, kept, t0 = FIRST, 0, 0, time.time()
    while d <= LAST:
        f = OUT / f"{d}.jsonl"
        n = finished.get(d.isoformat())
        if n is None or not f.exists() or sum(1 for _ in open(f)) != n:
            rows = day_rows(auth, d.isoformat())
            tmp = f.with_suffix(".part")
            tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
            os.replace(tmp, f)  # a day file exists only once it is complete
            with open(MANIFEST, "a") as m:
                m.write(json.dumps({"day": d.isoformat(), "hits": len(rows)}) + "\n")
            done, kept = done + 1, kept + len(rows)
            if done % 50 == 0:
                print(f"{d}: {done} days fetched, {kept:,} companies, {time.time() - t0:.0f}s", flush=True)
        d += timedelta(days=1)
    print(f"finished: {done} new days, {kept:,} companies", flush=True)


if __name__ == "__main__":
    main()
