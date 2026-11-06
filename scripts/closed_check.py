"""Phase B gate: does live snapshot + closed companies (Companies House API) reproduce the official totals?

Run: .venv/bin/python scripts/closed_check.py 2024-Q4
Uses the advanced search API's hit counts only (one request per company type and status, well under the
600 per 5 minutes limit). The key is read from .env and never printed.
"""
import base64
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.company-information.service.gov.uk/advanced-search/companies"
# The API's names for coverage.py's COMPANY_TYPES (CICs are "ltd" with a subtype, so already included).
TYPES = ["ltd", "plc", "private-unlimited", "private-unlimited-nsc", "private-limited-guarant-nsc",
         "private-limited-guarant-nsc-limited-exemption"]
CLOSED = ["dissolved", "converted-closed", "removed", "closed"]  # statuses the snapshot leaves out


def key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("COMPANIES_HOUSE_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("COMPANIES_HOUSE_API_KEY missing from .env")


def hits(auth: str, **params) -> int:
    url = API + "?" + urllib.parse.urlencode({**params, "size": 1})
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req, timeout=30) as r:
            return int(json.load(r).get("hits", 0))
    except urllib.error.HTTPError as e:
        if e.code == 404 and not e.read():  # "no results" is a bodiless 404; bad values are a 400 (probed 2 Nov)
            return 0
        raise


def main() -> None:
    q = sys.argv[1] if len(sys.argv) > 1 else "2024-Q4"
    y, n = int(q[:4]), int(q[-1])
    lo, hi = f"{y}-{3 * n - 2:02d}-01", f"{y}-{3 * n:02d}-{[31, 30, 30, 31][n - 1]}"
    auth = base64.b64encode(f"{key()}:".encode()).decode()
    total = {}
    for t in TYPES:
        for s in CLOSED:
            total[(t, s)] = hits(auth, company_type=t, company_status=s, incorporated_from=lo, incorporated_to=hi)
            time.sleep(0.6)  # ponytail: fixed pacing, a token bucket if this ever runs at scale
    closed = sum(total.values())
    row = next(r for r in csv.DictReader(open(ROOT / "active/coverage/coverage.csv"))
               if r["quarter"] == q and r["type"] == "companies")
    snap, official = int(row["snapshot"]), int(row["official"])
    print(json.dumps({f"{t}/{s}": v for (t, s), v in total.items() if v}, indent=1))
    print(f"{q}: snapshot {snap:,} + closed {closed:,} = {snap + closed:,} vs official {official:,} "
          f"({(snap + closed) / official - 1:+.1%})")


if __name__ == "__main__":
    main()
