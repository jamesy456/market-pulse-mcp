"""Market Pulse MCP server: read-only counts of new companies (still live, or including those since dissolved)
and one-year survival, from the summary grid.

Run: .venv/bin/python src/server.py   (stdio)
"""
import logging
import re
from math import sqrt
import threading
import time
import unicodedata
from datetime import date
from functools import cache, wraps
from pathlib import Path
from typing import Annotated, Literal

import duckdb
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from bundles import BUNDLES, DIVISIONS, WORDS
from release import CELL_VAR, SMALL, SMALL_NOTE, TEST_NOTE, change, odds_z, rate_range, release, share_change, share_z, z_needed

GRID = Path(__file__).resolve().parent.parent / "data/serve.duckdb"  # protected tables only, no raw counts
QUARTER = re.compile(r"(20\d\d)-Q([1-4])", re.ASCII)
AREA_CODE = re.compile(r"[EWS]\d{8}", re.ASCII)
SIC_CODE = re.compile(r"\d{2,5}", re.ASCII)  # 5 digits = one code; 2-4 digits = every code in that division/group/class
NO_ACTIVITY = "none"  # grid bucket for "None Supplied" and 99999 (dormant)
ALL = "all"  # every code plus 'none'
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
TABLES = {f"p_{t}{s}" for t in ("uk", "area", "mass") for s in ("", "_closed", "_gone")}
REQUIRED = TABLES | {"p_agg", "p_agg_closed", "p_agg_gone", "p_pre2021", "p_pre2021_mass", "areas", "regions", "sic", "meta"}
GAP_QUARTER = 2023 * 4 + 2  # 2023-Q2: open + closed is 178 companies short of the official count (DECISIONS.md)

# A misspelt option must be refused: ignored, it would answer for the default period without saying so. Set before any
# tool is defined. Not a public setting, so a test fails if an SDK upgrade drops it.
ArgModelBase.model_config["extra"] = "forbid"

LOCKED = {"enable_external_access": False, "autoinstall_known_extensions": False, "autoload_known_extensions": False,
          "lock_configuration": True}

_con = None
_lock, _local = threading.Lock(), threading.local()
log = logging.getLogger("market-pulse")
NO_DATA = ("NO_DATA: this server's data file is missing, damaged or from an older version, so it can't answer, and "
           "trying again won't help. Whoever runs it needs to build the data: see 'For whoever runs it' in the README.")


def db() -> duckdb.DuckDBPyConnection:
    """One cursor per thread: the MCP SDK runs tool calls in parallel on worker threads, and a DuckDB connection
    isn't thread-safe (security panel: 12 parallel calls returned 3 wrong answers on one shared connection)."""
    global _con
    cur = getattr(_local, "con", None)
    if cur is None:
        with _lock:
            if _con is None:
                try:
                    con = duckdb.connect(str(GRID), read_only=True, config=LOCKED)
                    missing = REQUIRED - {t for t, in con.execute(
                        "SELECT table_name FROM information_schema.tables").fetchall()}
                    if missing:
                        raise duckdb.Error(f"tables missing: {sorted(missing)}")
                except duckdb.Error:
                    log.exception("can't read %s", GRID)
                    raise ToolError(NO_DATA) from None
                _con = con
            cur = _local.con = _con.cursor()
    return cur


def meta() -> dict:
    return dict(db().execute("SELECT key, value FROM meta").fetchall())


def last_complete_quarter(snapshot: date) -> tuple[int, int]:
    q = (snapshot.month - 1) // 3  # quarters fully before the snapshot month's quarter
    return (snapshot.year, q) if q else (snapshot.year - 1, 4)


class Caveat(BaseModel):
    text: str
    must_quote: bool


class Excluded(BaseModel):
    mass_postcode_companies: str = Field(description="Companies at formation-agent postcodes left out (rounded)")
    unmatched_pct: float = Field(description="Share of companies whose postcode could not be placed in an area. In "
                                             "registrations_against_closures, registered companies only: the area "
                                             "caveat gives the dissolved share")


class CountResult(BaseModel):
    answer: str = Field(description="The summary plus both must-quote caveats, ready to pass on as one text.")
    summary: str = Field(description="Quote this sentence word for word.")
    rows: list[dict]
    snapshot_date: str
    snapshot_sha256: str
    caveats: list[Caveat] = Field(description="The first two are must-quote: include them in any answer.")
    excluded: Excluded


mcp = MCPServer(
    "market-pulse",
    instructions=(
        "Counts of UK companies registered in a period that are still live in one Companies House snapshot, or "
        "including those dissolved by the snapshot date, and the share not dissolved within a year. "
        "Always quote `summary` word for word and both must-quote caveats (`answer` holds all three together, for "
        "clients that pass on one field). Start the reply with them and keep any extra explanation brief. If the "
        "user asked for rows or a table, include the rows they asked for. If a bundle was used, say it is approximate "
        "and what it misses. Otherwise offer more detail (the rows, the other caveats, what the codes cover) rather "
        "than giving it unasked. Never state an exact number "
        "for a count shown as 'under 10 (rounded)' or 'too few to number for certain', and never work one out by "
        "subtracting other numbers. Answers about one area at a time are rounded estimates: putting them in order "
        "doesn't show which of the areas a breakdown leaves unnumbered truly has more companies. "
        "Always say which SIC codes an answer covers: the choice of codes can change the answer. If a code is "
        "rejected, ask the user which industry they meant; never answer for a different code in its place. "
        "To say which of two places has more or grew faster, use compare_two_areas, not two separate answers. "
        "For what is growing or shrinking in a place across all industries, use breakdown_by_industry. "
        "For how many companies are live in a place now, whatever year they were registered, use "
        "count_companies_live_now. "
        "For where most companies in an industry are, use largest_areas; for a place's biggest industries, use "
        "largest_industries. Never order places or industries yourself from separate answers or breakdown rows. "
        "In a largest list, keep rows whose likely ranks overlap together as a group in any order: never say one is next, "
        "follows or is ahead of another, and never call them tied. "
        "To ask whether more companies were registered or dissolved in a period, as in 'more opening than closing' or "
        "'closing faster than they open', use registrations_against_closures: it compares counts in one period, and "
        "can't show whether closures are speeding up. "
        "For everyday industries (AI, e-commerce, coffee shops, barbers...), find_sic offers ready-made bundles: pass "
        "the bundle id in sic_codes and tell the user it is approximate and what it misses. "
        "Regions and nations (London, North West, Wales, Scotland and so on) work in the count and compare tools: find "
        "them with find_area. Never add up council areas yourself; ask for the region or nation. "
        "This data can't answer some questions; say so and name the source instead of offering a figure from here as "
        "if it answered them: sole traders and partnerships (the government's yearly 'Business population estimates for "
        "the UK and regions', which are estimates); yearly business births and deaths before 2021, or of businesses rather than "
        "companies (ONS 'Business demography, UK'); businesses trading now (ONS 'UK business: activity, size and location', "
        "which counts VAT- or PAYE-registered businesses, a stand-in for those trading). Postcode or street level isn't "
        "available, to protect single companies: offer the council area."
    ),
)


def coded(fn):
    """Turn any unexpected failure into a coded error with no internals."""
    @wraps(fn)
    def run(*args, **kwargs):
        start, outcome = time.perf_counter(), "ok"
        try:
            return fn(*args, **kwargs)
        except ToolError as e:
            outcome = str(e).split(":")[0]
            raise
        except Exception:
            outcome = "INTERNAL"
            # stderr only (the client's MCP log), never the answer. The search tools take free text, which could hold
            # anything a user typed, so only their name is logged; the others take codes, quarters and flags.
            asked = "" if fn.__name__.startswith("find_") else f" while answering {(kwargs or args)!r:.300}"
            log.exception("%s failed%s", fn.__name__, asked)
            raise ToolError("INTERNAL: the query failed; try again or simplify it") from None
        finally:
            # Field names only, never values: the search tools take whatever a user typed.
            log.info("%s %s %.0f ms, fields %s", fn.__name__, outcome, (time.perf_counter() - start) * 1000, sorted(kwargs))
    return run


@mcp.tool(annotations=READ_ONLY)
@coded
def find_sic(text: str = Field(min_length=2, max_length=60)) -> list[dict]:
    """Find SIC 2007 codes for an industry. Everyday words (AI, coffee shop, barber, e-commerce) first return ready-made
    bundles: approximate code sets, with what they include and miss. Pass a bundle's id in sic_codes and say it is
    approximate. Then codes for that activity, then codes whose description contains the words (whole words, up to
    15, sorted by code, not relevance: keep only the ones for the activity asked about), then their 3-digit groups.
    For a broad industry ("cleaning"), pass the group code (e.g. "812") so every code in it is counted. Name the codes
    you used in your answer."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()  # café -> cafe
    if not re.fullmatch(r"[A-Za-z0-9\s,'&()-]+", text):
        raise ToolError("BAD_INPUT: use letters, digits and spaces only")
    t = norm(text)
    if len(t) < 2:
        raise ToolError("BAD_INPUT: give at least 2 letters or digits")
    found, seen = [], set()
    for w, codes in WORDS.items():  # one activity's own code first (review codex-bundles-v2: "nail salon")
        for c in codes if has_word(w, t) else ():
            if c not in seen:
                seen.add(c)
                found.append({"code": c, "description": db().execute(
                    "SELECT any_value(description) FROM sic WHERE code = ?", [c]).fetchone()[0]})
    found += [{"code": k, "description": f"Ready-made bundle, approximate: {label}. Codes: {', '.join(codes)}. {note} "
                                         f"Pass '{k}' as a code."}
              for k, (label, codes, _, note, words) in BUNDLES.items() if any(has_word(w, t) for w in words)]
    # user reviews: substring matching found cattle farming for "AI" (dAIry) and petroleum for "pet"
    pattern = r"\b" + "[ -]".join(w[:-1] + "(y|ies)" if w.endswith("y") else re.sub(r"([^a-z0-9])", r"\\\1", w) + "(s|es)?"
                                    for w in t.split()) + r"\b"
    rows = [(c, d) for c, d in db().execute(
        "SELECT code, any_value(description) FROM sic WHERE regexp_matches(description, ?, 'i') OR code LIKE ? "
        "GROUP BY code ORDER BY code LIMIT 15", [pattern, f"{t}%"]).fetchall() if c not in seen]
    found += [{"code": c, "description": d} for c, d in rows]
    for g in dict.fromkeys(c[:3] for c, _ in rows):  # benchmark: "cleaning" flips direction with the code choice
        members = db().execute("SELECT code, any_value(description) FROM sic WHERE code LIKE ? GROUP BY code "
                               "ORDER BY code", [f"{g}%"]).fetchall()
        names = "; ".join(f"{c} {d}" for c, d in members)
        found.append({"code": g, "description": f"Group {g}xx, {len(members)} code{'s' * (len(members) > 1)}: {names[:300]}"})
    if re.search(r"none|no activity|dormant|99999|not stated", t):
        found.insert(0, {"code": NO_ACTIVITY, "description": "No activity stated: pass 'none'. Covers 'None Supplied' "
                                                             "and 99999 (dormant company), which isn't an activity"})
    if not found:
        raise ToolError(f"NO_MATCH: nothing matches '{t[:40]}'. Try one everyday word ('coffee', 'builder', "
                        f"'software'), a broader industry, or a 2-digit division code. Ready-made bundles: "
                        f"{', '.join(BUNDLES)}.")
    for f in found:  # outsider test: "tattoo" led to a catch-all code with no warning
        if len(f["code"]) == 5 and "n.e.c" in f["description"].lower():
            f["description"] += " (a catch-all code: most companies in it don't do this activity)"
    return found


def singular(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"  # nurseries -> nursery
    if w.endswith(("ches", "shes", "sses", "xes")):
        return w[:-2]
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


def norm(text: str) -> str:
    """Lower case, hyphens and punctuation as spaces, each word singular: 'E-commerce shops' -> 'e commerce shop'."""
    return " ".join(singular(w) for w in re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def has_word(word: str, text: str) -> bool:
    """Whole word or phrase after norm(): 'ai' is in 'ai startups', not in 'dairy'. '=word' must be the whole text."""
    return norm(word[1:]) == text if word.startswith("=") else f" {norm(word)} " in f" {text} "


PLAIN_SQL = "regexp_replace(regexp_replace(replace(lower({}), '&', ' and '), '[''.]', '', 'g'), '[^a-z0-9]+', ' ', 'g')"


def plain_name(text: str) -> str:
    """A place name as PLAIN_SQL leaves it, so "Stoke on Trent", "Kings Lynn" and "Argyll & Bute" find theirs."""
    t = re.sub(r"[^a-z0-9]+", " ", re.sub(r"['.]", "", text.lower().replace("&", " and "))).strip()
    return re.sub(r"(?<=\w)\s+((city |county |borough |district )?council|city)$", "", t.removeprefix("the "))


@mcp.tool(annotations=READ_ONLY)
@coded
def find_area(text: str = Field(min_length=2, max_length=60)) -> list[dict]:
    """Find areas by name, matching from the start of any word: regions and nations first (London means all 33 London
    council areas; the City of London is one small council area), then local authority districts (England, Wales,
    Scotland). A county isn't an area here, so a county's name may find one district in it: check the name. Northern
    Ireland has no area breakdown."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()  # Ynys Môn -> Ynys Mon
    if not re.fullmatch(r"[A-Za-z0-9\s,'&().-]+", text):
        raise ToolError("BAD_INPUT: use letters, digits, spaces and everyday punctuation only")
    t = plain_name(text)
    if len(t) < 2:
        raise ToolError("BAD_INPUT: give at least 2 letters or digits")
    like, code = f"% {t}%", text.strip().upper()
    regions = db().execute(f"SELECT rgncd, rgnnm, count(*) FROM regions WHERE ' ' || {PLAIN_SQL.format('rgnnm')} LIKE ? "
                           "OR rgncd = ? GROUP BY ALL ORDER BY rgnnm", [like, code]).fetchall()
    rows = db().execute(
        f"SELECT ladcd, ladnm FROM areas WHERE (' ' || {PLAIN_SQL.format('ladnm')} LIKE ? OR ladcd = ?) AND NOT northern_ireland "
        "AND ladcd <> 'unmatched' ORDER BY ladnm LIMIT 15", [like, code]).fetchall()
    found = ([{"code": c, "name": n, "type": f"{'nation' if c[0] in 'SW' else 'region'}: all {k} council areas in it"}
              for c, n, k in regions] + [{"code": c, "name": n, "type": "council area"} for c, n in rows])
    # Outsider test: an empty list read as "that place doesn't exist", and "England" found only East of England
    if not found or t in ("england", "gb", "great britain", "britain", "uk", "united kingdom"):
        raise ToolError(f"NO_MATCH: no region, nation or council area matches {text[:12]!r}. Check the spelling, or "
                        "try one word of the name. Councils merged since 2021 are under today's council. For the whole "
                        "country use area 'UK'; England on its own isn't available. Northern Ireland has no area "
                        "breakdown: UK totals only.")
    return found


# User reviews, batch A5: a refusal names the nearest thing that can be answered, or the right outside source
# (names and coverage checked on GOV.UK and ONS, 3 Nov 2026).
EARLIER = ("For years before 2021, ONS's yearly 'Business demography, UK' counts business births and deaths by council "
           "area; it counts businesses registered for VAT or PAYE, not company registrations, so it isn't the same measure.")


def next_step(sics: list[str], areas: tuple[str, ...], lo: int) -> str:
    """Review codex-a5: only the ways to widen the question that this one still has, and say a wider question is a
    different question."""
    councils = [a for a in areas if a != "UK" and len(members(a)) == 1]  # review v2: never a region for 'UK'
    ways = ([] if set(all_codes()) <= set(sics) else ["a wider group of codes"]) + (
        ["a longer period"] if lo > 2021 * 4 + 1 else []) + (
        [f"the region or nation {area_name(a)} is in" for a in councils])
    if not ways:
        return " This data can't answer this question at this level."
    return (f" A wider question ({', or '.join(ways)}) may have enough to answer, though it answers a different "
            "question" + (": widening either area changes the comparison." if len(areas) > 1 else "."))


@cache
def all_codes() -> tuple[str, ...]:
    return tuple(r[0] for r in db().execute("SELECT DISTINCT code FROM sic").fetchall())


def parse_quarter(q: str, snap: date) -> int:
    m = QUARTER.fullmatch(q)
    if not m:
        raise ToolError(f"BAD_QUARTER: use YYYY-Qn, e.g. 2026-Q3 (got {q[:12]!r})")
    y, n = int(m[1]), int(m[2])
    ly, lq = last_complete_quarter(snap)
    if y * 4 + n < 2021 * 4 + 1:
        raise ToolError(f"OUT_OF_RANGE: quarters run from 2021-Q1 to {ly}-Q{lq}. {EARLIER}")
    if y * 4 + n > ly * 4 + lq:
        raise ToolError(f"OUT_OF_RANGE: quarters run from 2021-Q1 to {ly}-Q{lq}")
    return y * 4 + n


def qname(k: int) -> str:
    return f"{(k - 1) // 4}-Q{(k - 1) % 4 + 1}"


# Break-it B5: told "each code must be 2-5 digits or 'none'", models answered for 'none' instead of the code asked for.
NO_SWAP = ("Ask the user which industry they meant, or look it up with find_sic; don't answer for a different code "
           "in its place.")


def expand_sics(sic_codes: list[str]) -> tuple[list[str], str]:
    """Validate codes, expand 2-4 digit prefixes to their 5-digit codes. Returns (codes, label for the summary)."""
    sic_codes = [NO_ACTIVITY if c == "99999" else c for c in sic_codes]  # break-it B5: dormant 99999 is in 'none'
    bundles = [c for c in dict.fromkeys(sic_codes) if c in BUNDLES]
    if bundles:  # ready-made bundles: their codes, labelled approximate
        plain = [c for c in sic_codes if c not in BUNDLES]
        codes, _ = expand_sics([c for b in bundles for c in BUNDLES[b][1]] + plain)
        names = " and ".join(f"'{BUNDLES[b][0]}'" for b in bundles)
        limits = "; ".join(BUNDLES[b][2] for b in bundles)  # review codex-bundles: the main limit, up front
        listed = ", ".join(dict.fromkeys(f"{c}{'x' * (5 - len(c))}" for b in bundles for c in BUNDLES[b][1]))
        label = f"the {names} bundle{'s' if len(bundles) > 1 else ''} (approximate: {limits}; SIC {listed})"
        return codes, label + (f" plus {expand_sics(plain)[1]}" if plain else "")
    if ALL in sic_codes:  # break-it B13: agents added up divisions by hand and couldn't show they covered every code
        codes = [r[0] for r in db().execute("SELECT DISTINCT code FROM sic ORDER BY code").fetchall()]
        return codes + [NO_ACTIVITY], "any SIC code (all industries, including no activity stated)"
    if not all(c == NO_ACTIVITY or SIC_CODE.fullmatch(c) for c in sic_codes):
        bad = next(c for c in sic_codes if not (c == NO_ACTIVITY or SIC_CODE.fullmatch(c)))
        raise ToolError(f"BAD_SIC: {bad[:12]!r} isn't a SIC code (codes are 2-5 digits). {NO_SWAP}")
    codes, labels = [], []
    for c in dict.fromkeys(sic_codes):  # review 4, F4: duplicates counted once
        if c == NO_ACTIVITY or len(c) == 5:
            if any(len(o) < 5 and o != NO_ACTIVITY and c.startswith(o) for o in sic_codes):
                continue  # review of phase A: already listed under its group
            if c != NO_ACTIVITY and not db().execute("SELECT 1 FROM sic WHERE code = ?", [c]).fetchone():
                # testing sweep: a mistyped code (12345) answered "fewer than 10 companies with SIC 12345"
                raise ToolError(f"BAD_SIC: no company in this data uses SIC {c}. {NO_SWAP}")
            codes.append(c)
            labels.append("no activity stated" if c == NO_ACTIVITY else f"SIC {c}")
            continue
        if any(o != c and len(o) < len(c) and c.startswith(o) for o in sic_codes if o != NO_ACTIVITY):
            continue  # review of phase A: its codes are already listed under the wider group
        members = [r[0] for r in db().execute("SELECT DISTINCT code FROM sic WHERE code LIKE ? ORDER BY code",
                                              [f"{c}%"]).fetchall()]  # c is digits only, so no LIKE wildcards
        if not members:
            raise ToolError(f"BAD_SIC: no SIC codes start with {c}. {NO_SWAP}")
        codes += members
        labels.append(f"SIC {c}{'x' * (5 - len(c))} ({len(members)} code{'s' * (len(members) > 1)}: {', '.join(members)})")
    return list(dict.fromkeys(codes)), ", ".join(labels)


@cache
def members(area: str) -> tuple[str, ...]:
    """The council areas an area code covers: every area in a region or nation, or the area itself."""
    rows = db().execute("SELECT ladcd FROM regions WHERE rgncd = ? ORDER BY ladcd", [area]).fetchall()
    return tuple(r[0] for r in rows) or (area,)


def area_name(area: str) -> str:
    if not AREA_CODE.fullmatch(area):
        raise ToolError("BAD_AREA: use a code from find_area, or 'UK' where this tool offers it (Northern Ireland: UK totals only)")
    region = db().execute("SELECT any_value(rgnnm) FROM regions WHERE rgncd = ?", [area]).fetchone()[0]
    if region:  # "the North West", "the East of England"; "London", "Wales", "Yorkshire and The Humber"
        return f"the {region}" if region.split()[0] in ("North", "South", "East", "West") else region
    found = db().execute("SELECT ladnm FROM areas WHERE ladcd = ? AND NOT northern_ireland", [area]).fetchone()
    if found is None:  # an unknown code is an error, not an answer about "None"
        raise ToolError("BAD_AREA: unknown area code; use find_area (Northern Ireland: UK totals only)")
    return found[0]


def span(lo: int, hi: int) -> str:
    return qname(lo) if lo == hi else f"{qname(lo)} to {qname(hi)}"


def covering(area: str) -> str:
    """' (all N council areas)' for a region or nation, so the reader knows what was added up; '' for one area."""
    n = len(members(area))
    return f" (all {n} council areas)" if n > 1 else ""


def bundle_notes(sic_codes: list[str]) -> tuple[str, ...]:
    return tuple(f"'{BUNDLES[b][0]}' is a ready-made, approximate bundle. {BUNDLES[b][3]}"
                 for b in dict.fromkeys(sic_codes) if b in BUNDLES)


def period(from_quarter: str | None, to_quarter: str | None, snap: date) -> tuple[int, int]:
    """One period: default the latest four quarters (from 2021-Q1 at the earliest)."""
    ly, lq = last_complete_quarter(snap)
    hi = parse_quarter(to_quarter, snap) if to_quarter else ly * 4 + lq
    lo = parse_quarter(from_quarter, snap) if from_quarter else max(hi - 3, 2021 * 4 + 1)
    if lo > hi:
        raise ToolError("BAD_RANGE: from_quarter is after to_quarter")
    return lo, hi


def window(from_quarter: str | None, to_quarter: str | None, against: str, snap: date) -> tuple[int, int, int, int]:
    """The later period (default: the latest four quarters) and the earlier one it is compared with: the same quarters
    a year before (a window over four quarters steps back whole years, so the two never overlap), or the period of
    the same length just before. User reviews: '2026 so far against the same months of 2025' had no answer."""
    lo2, hi2 = period(from_quarter, to_quarter, snap)
    n = hi2 - lo2 + 1
    back = 4 * -(-n // 4) if against == "year_before" else n
    if lo2 - back < 2021 * 4 + 1:
        raise ToolError("OUT_OF_RANGE: the earlier period would start before 2021-Q1. Use a later or shorter period")
    return lo2 - back, hi2 - back, lo2, hi2


FROM_Q = Annotated[str | None, Field(description="YYYY-Qn starting the later period; default four quarters before "
                                                 "to_quarter's end, so a whole year")]
TO_Q = Annotated[str | None, Field(description="YYYY-Qn ending the later period; default the last complete quarter")]
LIST_FROM = Annotated[str | None, Field(description="YYYY-Qn starting the period; default four quarters before "
                                                    "to_quarter's end, so a whole year")]
AGAINST = Annotated[Literal["year_before", "previous"], Field(
    description="Compare with the same quarters a year before (default; '2026-Q1 to Q3 against 2025-Q1 to Q3'; a "
                "period longer than four quarters goes back whole years, e.g. eight quarters against the eight before, "
                "so the two never overlap) or with the period of the same length just before. Answers name both "
                "periods")]
CLOSED_IN = Annotated[bool, Field(description="True (default): count companies registered in each period, including "
                                              "those since dissolved, so an older period isn't shrunk by closures. "
                                              "False: still open only")]


def protected_sum(table: str, sics: list[str], lo: int, hi: int, area: str | None = None, by: str = "",
                  age: str | None = None, floor: bool = False) -> dict:
    """Sum protected cells. Only the p_* tables are ever read; `by` is one of three fixed strings, never user text.
    Closed tables sum both age buckets unless `age` picks one. floor=True sums the fewest companies each cell can
    hold: one shown as p holds at least p - 4 (rounding moves a count up by at most 4), one shown as 0 at least 0.
    Lists pick areas on this, never on the shown sum (testing phase: 7 vape areas shown as 10-15 were really under 10)."""
    if (table not in TABLES or by not in ("", "ladcd", "year, quarter", "sic")  # survives python -O
            or age not in (None, "under_1y", "1y_plus") or (age and not table.endswith("_closed"))):
        raise ValueError("protected_sum: unexpected table, grouping or age")
    where = "sic IN (SELECT unnest(?)) AND year * 4 + quarter BETWEEN ? AND ?"
    params: list = [sics, lo, hi]
    if area:  # a council area, or every council area in a region or nation
        where += " AND ladcd IN (SELECT unnest(?))"
        params.append(list(members(area)))
    if age:
        where += " AND age = ?"
        params.append(age)
    value = "greatest(protected - 4, 0)" if floor else "protected"
    sql = (f"SELECT {by + ', ' if by else ''}coalesce(sum({value}), 0)::INTEGER FROM {table} WHERE {where}"
           + (f" GROUP BY {by}" if by else ""))
    return {r[:-1]: r[-1] for r in db().execute(sql, params).fetchall()}


def with_closed(table: str, closed: bool, *args, floor: bool = False) -> dict:
    """Live protected sums, plus the closed ones (both ages) when asked: each is its own protected cell."""
    live = protected_sum(table, *args, floor=floor)
    if not closed:
        return live
    gone = protected_sum(f"{table}_closed", *args, floor=floor)
    return {k: live.get(k, 0) + gone.get(k, 0) for k in live.keys() | gone.keys()}


AGG_TABLES = ("p_agg", "p_agg_closed", "p_pre2021", "p_agg_gone")
# Batch B (scripts/build_levels.py, INDEPENDENT): a total shown at OWN or more was rounded once on its own; a smaller
# one was published as the sum of its parts' shown values, so it carries the rounding of every cell under it.
OWN = 50
PARTS_NOTE = ("Some totals are rounded on their own, separately from their parts (quarters, areas or industries), so "
              "the parts may not add up exactly to the total.")


@cache
def n_gb() -> int:
    """Council areas in Great Britain plus the unmatched-postcode row: the parts of a 'GB' total."""
    return db().execute("SELECT count(*) FROM areas WHERE NOT northern_ireland").fetchone()[0]


def cover(sics: list[str]) -> dict[str, int]:
    """The fewest published industry totals (whole divisions, then whole groups, then single codes) that add up to
    exactly these codes, each with how many codes it covers."""
    s, codes = set(sics), all_codes()
    if s >= {*codes, NO_ACTIVITY}:
        return {ALL: len(codes) + 1}
    out = {NO_ACTIVITY: 1} if NO_ACTIVITY in s else {}
    for d in sorted({c[:2] for c in s - {NO_ACTIVITY}}):
        under = {c for c in codes if c.startswith(d)}
        if s >= under:
            out[d] = len(under)
            continue
        for g in sorted({c[:3] for c in s - {NO_ACTIVITY} if c.startswith(d)}):
            under = {c for c in codes if c.startswith(g)}
            out.update({g: len(under)} if s >= under else {c: 1 for c in sorted(s) if c.startswith(g)})
    return out


def agg(table: str, sics: list[str], lo: int, hi: int, places: list[str], by: str = "", age: str | None = None,
        nodes: dict[str, int] | None = None) -> dict:
    """Sum published totals; per key, (value, cells). places: 'UK', 'GB' (every council area plus unmatched; no
    agents or Northern Ireland), regions or nations, council areas. Cells come from shown values and the question's
    shape, never from whether a cell is present (a present cell shown 0 holds 1-4 companies): a council x code or
    UK x code cell, or a total shown at OWN or more, is one cell; a smaller total is every cell under it.
    `nodes` (industry total -> codes it covers) defaults to cover(sics). p_pre2021 has no quarters (lo, hi unused)."""
    if (table not in AGG_TABLES or by not in ("", "geo", "year, quarter", "ind")  # survives python -O
            or age not in (None, "under_1y", "1y_plus") or (age and table != "p_agg_closed")):
        raise ValueError("agg: unexpected table, grouping or age")
    nodes = nodes or cover(sics)
    places = list(dict.fromkeys(places))
    params = {"inds": list(nodes), "codes": list(nodes.values()), "geos": places,
              "size": [1 if p == "UK" else n_gb() if p == "GB" else len(members(p)) for p in places],
              "base": [p == "UK" or (p != "GB" and members(p) == (p,)) for p in places]}
    src = ["(SELECT unnest($inds) AS ind, unnest($codes) AS codes) n",
           "(SELECT unnest($geos) AS geo, unnest($size) AS size, unnest($base) AS base) g"]
    on = "p.geo = g.geo AND p.ind = n.ind"
    if table != "p_pre2021":
        src.append("(SELECT (k - 1) // 4 AS year, (k - 1) % 4 + 1 AS quarter FROM range($lo, $hi + 1) r(k)) t")
        on += " AND p.year = t.year AND p.quarter = t.quarter"
        params |= {"lo": lo, "hi": hi}
    if table == "p_agg_closed":
        src.append("(SELECT unnest($ages) AS age) a")
        on += " AND p.age = a.age"
        params["ages"] = [age] if age else ["under_1y", "1y_plus"]
    key = {"": "", "geo": "g.geo", "year, quarter": "t.year, t.quarter", "ind": "n.ind"}[by]
    sql = (f"SELECT {key + ', ' if key else ''}coalesce(sum(p.protected), 0)::INTEGER, "
           f"sum(CASE WHEN coalesce(p.protected, 0) >= {OWN} OR (g.base AND (n.ind = '{NO_ACTIVITY}' OR len(n.ind) = 5)) "
           f"THEN 1 ELSE n.codes * g.size END)::INTEGER FROM {' CROSS JOIN '.join(src)} LEFT JOIN {table} p ON {on}"
           + (f" GROUP BY {key}" if key else ""))
    return {tuple(r[:-2]): (r[-2], r[-1]) for r in db().execute(sql, params).fetchall()}


def totals(sics: list[str], lo: int, hi: int, places: list[str], closed: bool = False, by: str = "",
           nodes: dict[str, int] | None = None) -> dict:
    """Live published totals, plus companies since dissolved (both ages) when asked: per key, (value, cells)."""
    out = agg("p_agg", sics, lo, hi, places, by, nodes=nodes)
    if closed:
        for k, (v, c) in agg("p_agg_closed", sics, lo, hi, places, by, nodes=nodes).items():
            x = out.get(k, (0, 0))
            out[k] = (x[0] + v, x[1] + c)
    return out


def total_of(sics: list[str], lo: int, hi: int, place: str, closed: bool = False,
          nodes: dict[str, int] | None = None) -> tuple[int, int]:
    """One place's total and its cells."""
    return totals(sics, lo, hi, [place], closed, nodes=nodes)[()]


def table_total(t: str, where: str = "") -> int:
    return db().execute(f"SELECT coalesce(sum(protected), 0) FROM {t} {where}").fetchone()[0]  # fixed names


@cache
def unmatched_with_closed() -> float:
    """Share of open and closed companies whose postcode isn't placed, from protected sums only."""
    out = sum(table_total(t, "WHERE ladcd = 'unmatched'") for t in ("p_area", "p_area_closed"))
    return round(100 * out / (table_total("p_uk") + table_total("p_uk_closed")), 2)


@cache
def unmatched_each_side() -> tuple[float, float]:
    """Shares of registered and of dissolved companies not placed, among those area answers keep (GB, no agents)."""
    def share(*tables: str) -> float:
        return round(100 * sum(table_total(t, "WHERE ladcd = 'unmatched'") for t in tables)
                     / sum(table_total(t) for t in tables), 2)
    return share("p_area", "p_area_closed"), share("p_area_gone")


def gap_note(lo: int, hi: int) -> tuple[str, ...]:
    return (("For 2023-Q2, companies here (open plus closed) are 178 short of Companies House's official count "
             "for that quarter (0.08%); the cause is unknown."),) if lo <= GAP_QUARTER <= hi else ()


# Trial 2 (James): London's share of GB fell with formation-agent addresses left out but rose with them in.
# scripts/check_agent_share.py: when agents are 20%+ of GB's companies, an area's share moves the other way with them put
# back in 6-7% of cases (London 14-15%), against 1-3% below 20%. A precautionary trigger from that sample (large single
# codes, one pair of years, still-open companies), not a sharp boundary (review codex-agent-warning.md).
AGENT_SHARE = 0.2


def agent_warning(sics: list[str], lo: int, hi: int, closed: bool = False) -> str:
    """A sentence for the summary when formation-agent addresses are a large share of GB's companies; else ''."""
    mass = sum(with_closed("p_mass", closed, sics, lo, hi).values())
    counted = sum(with_closed("p_area", closed, sics, lo, hi).values())
    if mass < 10 or mass < AGENT_SHARE * (mass + counted):
        return ""
    with_these = "" if set(all_codes()) <= set(sics) else " with these codes"
    return (f" About {mass / (mass + counted):.0%} of Great Britain's companies{with_these} registered in "
            f"{qname(lo) if lo == hi else f'{qname(lo)} to {qname(hi)}'} are at formation-agent addresses, which area figures leave out, so "
            "comparing areas, or an area with Great Britain, may mislead.")


def caveats(snap: date, by_area: bool, mass_text: str, unmatched: float, extra: tuple[str, ...] = (),
            closed: bool = False, first: str | None = None, area_text: str | None = None,
            across: str = "") -> list[Caveat]:
    return [
        Caveat(must_quote=True, text=first if first else (
            f"These count the companies registered in this period, including those dissolved before "
            f"{snap:%-d %B %Y}. Dissolved is not the same as stopped trading, and closures here lag real failures: "
            "unless its owners apply to close it, a company is struck off only after it misses a filing deadline, "
            "more than a year after it starts.")
            if closed else (
            f"These are companies registered in this period that were still open on {snap:%-d %B %Y}. "
            "Companies that have since closed aren't counted, so older periods look lower than they really were.")),
        Caveat(must_quote=True, text=area_text or (
            f"Area means the company's registered address, not where it works. {mass_text} companies at "
            f"formation-agent addresses are left out{across}, and {unmatched}% of addresses couldn't be placed in an area.")
            if by_area else (
            "This is a UK total, so it includes companies at formation-agent addresses and in Northern Ireland. "
            "Registered address is not where a company works.")),
        *([Caveat(must_quote=False, text="Companies in liquidation or being struck off still count as open.")]
          if closed else []),  # e2e Q3: kept out of the must-quote caveat so that one stays short enough to be quoted
        *(Caveat(must_quote=False, text=t) for t in extra),
        Caveat(must_quote=False, text=(
            "Every figure is built from counts that were randomly rounded to 5 to protect small numbers, so small "
            "counts are approximate: one shown as 10 could really be as low as 2. The likely range allows for this.")),
        Caveat(must_quote=False, text=(  # break-it B15: agents read registrations as cafés opened
            "A company registration is not a business opening: some companies never trade, and one business can "
            "run several companies.")),
        Caveat(must_quote=False, text="Only each company's first SIC code is used; companies list it themselves."),
        Caveat(must_quote=False, text=("Covers private limited companies, PLCs and LLPs; not sole traders or partnerships. "
                                       "For estimates that include them, see the government's yearly 'Business "
                                       "population estimates for the UK and regions'.")),
    ]


def floored(r: dict, live: tuple[int, int]) -> dict:
    """A release() of a count with dissolved companies: its low end can't be below the still-open count's."""
    low = release(*live)["range"]
    if r["range"] and low:
        r["range"][0] = max(r["range"][0], low[0])
    return r


def recent(closed: bool, hi: int, snap: date) -> str:
    """CAUTIOUS when a period with dissolved companies counted runs into the latest year; else ''."""
    ly, lq = last_complete_quarter(snap)
    return CAUTIOUS if closed and hi > ly * 4 + lq - 4 else ""


def about(n: int) -> str:
    r = release(n)
    return f"about {r['display']}" if r["count"] is not None else SMALL


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


# Phase C: a "likely (rounding could explain it)" tier, from a test that ignored rounding, named areas that the exact
# counts don't support (rounding had moved their small cells). Only verdicts that allow for rounding are given.
# v4 review: a test on rounded counts can still be misled by rounding (Tower Hamlets food 2021: cautious z 2.59,
# exact 0.19), so no verdict claims to hold "even allowing for rounding".
NOT_CERTAIN = "on a test that allows for rounding (not certain: rounding can still mislead it)"
RANK_VERDICTS = [f"stands out {NOT_CERTAIN}", "could be chance among this many areas",
                 "clear "]  # last one gets "fall/rise instead"
PICKED_CAVEAT = ("This verdict tests one area on its own. If the area was picked because it ranked high among many, "
                 "some apparent change is expected by chance; use the ranking's verdict instead.")
SHARE_CAVEAT = ("A share of Great Britain on still-open counts compares like with like only if companies here close "
                "at about the same rate as elsewhere; include_closed true removes that doubt.")
# Final review, scripts/check_rank_basis.py: of 32 areas the ranking named on still-open counts, 11 held on exact counts
# with dissolved companies and 3 went clearly the other way; on counts with dissolved, all 39 held.
LIVE_NOTE = (" These counts leave out closed companies, so older periods look lower and a change can come from closures "
             "alone: include_closed true compares periods fairly.")
CAUTIOUS = (" This test is cautious for a recent period with dissolved companies counted: few have dissolved yet and "
            "those few carry a lot of rounding noise, so no clear answer doesn't show that nothing changed.")
SEASON = "registrations vary by season (the first quarter was the busiest in four of the five years from 2021 to 2025)"
# Break-it B11: models turned "nothing stands out" into a flat "No" to "is X the fastest-growing?", even with the
# caveat, so every ranking summary now opens by saying it can't answer that either way.
RANK_LIMIT = ("This can't say which area grew fastest, or answer yes or no to whether a named area did: it only "
              "lists areas whose change in share of Great Britain stands out on a test that allows for rounding and "
              "chance, though not with certainty. ")
PAIR_CAVEAT = ("This tests one pair of areas. If they were picked as the most extreme among many, some apparent "
               "difference is expected by chance.")
RANK_CAVEAT = ("This ranks evidence, not growth: an area missing from these rows is not shown to be growing more slowly. "
               "To answer about a named area, use compare_area_with_great_britain.")  # break-it B11


def result(summary: str, rows: list[dict], m: dict, snap: date, by_area: bool, mass: int, cells: int,
           extra: tuple[str, ...] = (), closed: bool = False, first: str | None = None,
           area_text: str | None = None, excluded: Excluded | None = None, across: str = "") -> CountResult:
    m_out = release(mass, cells)
    unmatched = unmatched_with_closed() if closed else float(m["unmatched_pct"])
    mass_text = f"About {m_out['display']}" if m_out["count"] is not None else cap(SMALL)
    summary += " Counts are built from randomly rounded figures and shown to the nearest 5, so they aren't exact."
    age = (date.today() - snap).days
    if age > 45:  # Companies House publishes a new snapshot each month
        summary += f" This snapshot is {age} days old, so newer data exists."
    if (SMALL in summary.lower() or SMALL in (area_text or "").lower()
            or any(SMALL in str(v) for r in rows for v in r.values())):
        summary += SMALL_NOTE
    cav = caveats(snap, by_area, mass_text, unmatched, extra, closed, first, area_text, across)
    return CountResult(answer=" ".join([summary, *(c.text for c in cav if c.must_quote)]), summary=summary, rows=rows,
                       snapshot_date=m["snapshot_date"], snapshot_sha256=m["snapshot_sha256"], caveats=cav,
                       excluded=excluded or Excluded(mass_postcode_companies=m_out["display"] if by_area
                                                     else "none (UK totals include them)", unmatched_pct=unmatched))


SICS_FIELD = Field(min_length=1, max_length=20,
                   description=("SIC codes from find_sic: 5 digits, a 2-4 digit group such as '812' for all of it, "
                                "or a ready-made bundle id such as 'ai-and-data' (approximate). "
                                "Choose codes for the activity asked about, e.g. cleaning: ['812']; digital and tech: "
                                "['62011', '62012', '62020', '62090', '63110', '63120', '58290']; every industry: "
                                "['all']. The choice can change the answer, so say which codes you used."))


@mcp.tool(annotations=READ_ONLY)
@coded
def count_incorporations_still_live(
    sic_codes: list[str] = SICS_FIELD,
    area: str = Field(description="'UK', a region or nation, or a council area code from find_area"),
    from_quarter: str = Field(description="YYYY-Qn, from 2021-Q1"),
    to_quarter: str = Field(description="YYYY-Qn, up to the last complete quarter"),
    group_by: Literal["none", "quarter", "area"] = "none",
    include_closed: bool = Field(False, description="True counts the companies registered in the period, including "
                                 "those dissolved by the snapshot date: the fairer way to compare periods. False: still open only"),
) -> CountResult:
    """Count companies (private limited, PLC and LLP) registered in the period with these primary SIC codes
    that are still live in the snapshot, or with include_closed the companies in this data registered, including those dissolved
    by the snapshot date (use this to compare periods fairly). Area answers leave out formation-agent postcodes."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, what = expand_sics(sic_codes)
    place = "the UK" if area == "UK" else area_name(area)
    n_here = 1 if area == "UK" else len(members(area))
    if area != "UK" and group_by == "area" and n_here == 1:
        raise ToolError("BAD_GROUP: group_by 'area' needs area 'UK', a region or a nation")
    if area == "UK" and group_by == "area":
        place = "local authorities in Great Britain (plus unmatched postcodes, excluding formation-agent addresses)"
    elif group_by == "area":
        place = f"the council areas of {place}"
    else:
        place += covering(area) if area != "UK" else ""
    lo, hi = parse_quarter(from_quarter, snap), parse_quarter(to_quarter, snap)
    if lo > hi:
        raise ToolError("BAD_RANGE: from_quarter is after to_quarter")

    # UK totals include agents and Northern Ireland; anything about areas leaves both out ('GB' for every area).
    by_area = area != "UK" or group_by == "area"
    one = None if area == "UK" else area
    where = one or ("GB" if by_area else "UK")
    closed = include_closed
    mass = sum(with_closed("p_mass", closed, sics, lo, hi, one).values()) if by_area else 0
    total, cells = total_of(sics, lo, hi, where, closed)

    # Every quarter or area in range gets a row, so a missing row can't mean "exactly 0". Cell counts come from shown
    # values and the question's shape (agg), never from which cells are present.
    if group_by == "quarter":
        counts = totals(sics, lo, hi, [where], closed, "year, quarter")
        keys = [((k - 1) // 4, (k - 1) % 4 + 1) for k in range(lo, hi + 1)]
        live = totals(sics, lo, hi, [where], False, "year, quarter") if closed else {}
        rows = [{"quarter": f"{y}-Q{q}", **(floored(release(*counts[y, q]), live[y, q]) if closed else release(*counts[y, q]))}
                for y, q in keys]
    elif group_by == "area":
        keys = db().execute("SELECT ladcd, ladnm FROM areas WHERE NOT northern_ireland ORDER BY ladnm").fetchall()
        if one:  # a region or nation: its council areas only
            keys = [k for k in keys if k[0] in members(one)]
        counts = totals(sics, lo, hi, [c for c, _ in keys], closed, "geo")
        floors = with_closed("p_area", closed, sics, lo, hi, one, "ladcd", floor=True)
        live = totals(sics, lo, hi, [c for c, _ in keys], False, "geo") if closed else {}

        def area_row(c: str, name: str) -> dict:
            if floors.get((c,), 0) >= 10:  # the floor never exceeds the shown count, so this is 10+ shown too
                r = release(*counts[c,])
                return {"area_code": c, "area_name": name, **(floored(r, live[c,]) if closed else r)}
            # One label for every row without 10 for certain: an "under N" cap was the top of a likely range, not
            # certain, and a higher cap, or "10+ shown" against "fewer than 10", only meant rounding went up (cases v2:
            # Nottingham read as the leader).
            return {"area_code": c, "area_name": name, "count": None, "display": "too few to number for certain",
                    "range": None, "low": True}
        rows = sorted((area_row(c, n) for c, n in keys),
                      key=lambda r: (r["count"] is None, -(r["count"] or 0), r["area_name"]))
    else:
        keys, rows = [], []
    hidden = sum(r["count"] is None for r in rows)  # only real rows are counted

    t = floored(release(total, cells), total_of(sics, lo, hi, where)) if closed else release(total, cells)
    period = from_quarter if lo == hi else f"{from_quarter} to {to_quarter}"
    lead = f"About {t['display']}" if t["count"] is not None else cap(SMALL)
    # Review 5, F2: an area breakdown's total can sum hundreds of mostly empty cells, so its honest range can be too
    # wide to help. It is left out, and the reader is pointed at the question without a breakdown instead.
    show_range = t["range"] and group_by != "area"
    summary = (f"{lead} companies with {what} " + (
               f"were registered in {period} in {place}, including those dissolved by {snap:%-d %B %Y}" if closed else
               f"registered in {period} in {place} were still open on {snap:%-d %B %Y}")
               + (f" (likely range {t['range'][0]:,}–{t['range'][1]:,})" if show_range else "") + ".")
    if by_area:
        summary += agent_warning(sics, lo, hi, closed)
    if closed:
        gone = agg("p_agg_closed", sics, lo, hi, [where])[()][0]
        summary += f" {cap(about(gone))} of them had been dissolved by {snap:%-d %B %Y}."
    if group_by == "area":
        summary += (" For a total with a likely range, ask for area 'UK' without an area breakdown; it also counts formation-agent "
                    "addresses and Northern Ireland, so it will be higher." if area == "UK" else
                    " For a total with a likely range, ask for this region or nation without an area breakdown.")
    if t["low"] and t["count"] is not None:
        summary += " This is a low or uncertain count, so treat it with caution."
    if group_by == "quarter" and len(keys) >= 2:
        (a, ca), (b, cb), first, last = *(counts[k] for k in (keys[0], keys[-1])), rows[0]["quarter"], rows[-1]["quarter"]
        if not closed:  # outsider test: a "clear increase" here came from closures, and vanished with them counted
            summary += f" No change is tested between {first} and {last}.{LIVE_NOTE}"
        elif keys[0][1] != keys[-1][1]:  # outsider test: Q1 to Q4 said "decrease" every year, Q4 to Q1 "increase"
            summary += (f" No change is tested between {first} and {last}, which are different times of year: {SEASON}. "
                        "Ask for the same quarter a year apart.")
        else:
            v = change(a, b, ca, cb)
            summary += f" {first} against {last}, the two ends only: {v}." + (recent(closed, hi, snap) if v == "no clear change" else "")
    if hidden:
        summary += (f" {hidden} {'row is' if hidden == 1 else 'rows are'} too few to number for certain, listed by "
                    f"name; their order is alphabetical and says nothing about which is larger. Asked about one at a "
                    f"time, such an area may show a rounded count, but putting those in order doesn't show which truly "
                    f"has more.")
    return result(summary, rows, m, snap, by_area, mass, cells,
                  (*bundle_notes(sic_codes), *((PARTS_NOTE,) if rows else ()), *(gap_note(lo, hi) if closed else ())),
                  closed)


@mcp.tool(annotations=READ_ONLY)
@coded
def compare_area_with_great_britain(
    sic_codes: list[str] = SICS_FIELD,
    area: str = Field(description="A council area, region or nation code from find_area"),
    to_quarter: TO_Q = None,
    from_quarter: FROM_Q = None,
    against: AGAINST = "year_before",
    include_closed: CLOSED_IN = True,
) -> CountResult:
    """One-call brief: is this industry growing faster or slower in this area than across Great Britain?
    Compares a period (default the latest four quarters) with the same quarters a year before, or the period just
    before: the area's count, Great Britain's, the area's share of GB with a significance test, how concentrated the
    industry is here (location quotient), and the quarterly trend. Formation-agent addresses are left out on both
    sides. If you picked this area from rank_areas_against_great_britain, quote the ranking's verdict instead: this
    tool tests one area on its own. To say which of two areas grew faster, use compare_two_areas."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, what = expand_sics(sic_codes)
    place = area_name(area)
    lo1, hi1, lo2, hi2 = window(from_quarter, to_quarter, against, snap)
    closed = include_closed
    (a1, ca1), (a2, ca2) = (total_of(sics, lo, hi, area, closed) for lo, hi in ((lo1, hi1), (lo2, hi2)))
    (g1, cg1), (g2, cg2) = (total_of(sics, lo, hi, "GB", closed) for lo, hi in ((lo1, hi1), (lo2, hi2)))
    mass = sum(sum(with_closed("p_mass", closed, sics, lo, hi, area).values()) for lo, hi in ((lo1, hi1), (lo2, hi2)))
    # The rest of GB is GB's total less this area's, each rounded on its own, so it carries both their rounding.
    verdict = share_change(a1, g1, a2, g2, (ca1, ca2), (cg1 + ca1, cg2 + ca2))
    p1, p2 = span(lo1, hi1), span(lo2, hi2)
    how = (f"were registered in {p2}, including those dissolved by {snap:%-d %B %Y}" if closed else
           f"registered in {p2} were still open on {snap:%-d %B %Y}")
    summary = (f"In {place}{covering(area)}, {about(a2)} companies with {what} {how}, against {about(a1)} from {p1}. "
               f"Across Great Britain, leaving out formation-agent addresses: {about(g2)} against {about(g1)}.")
    if not closed:
        summary += LIVE_NOTE
    if verdict == "too few to compare":
        summary += " Too few companies here to compare shares." + next_step(sics, (area,), lo1)
    else:
        summary += f" {cap(place)}'s share of Great Britain went from {a1 / g1:.2%} to {a2 / g2:.2%}: {verdict}."
        summary += recent(closed, hi2, snap) if verdict.startswith("no clear") else ""
    summary += agent_warning(sics, lo2, hi2, closed)

    # Location quotient: this industry's share of all new companies here, against the same share across GB.
    everything = {ALL: len(all_codes()) + 1}
    here_all = total_of(sics, lo2, hi2, area, closed, everything)[0]
    gb_all = total_of(sics, lo2, hi2, "GB", closed, everything)[0]
    if min(a2, here_all) >= 10 and g2 and ALL not in sic_codes:  # user review: "100.0% of all new companies"
        lq = (a2 / here_all) / (g2 / gb_all)
        summary += (f" This industry makes up {a2 / here_all:.1%} of all new companies in {place}, against "
                    f"{g2 / gb_all:.1%} across Great Britain ({lq:.1f} times the national level).")

    here_q, gb_q = (totals(sics, lo1, hi2, [x], closed, "year, quarter") for x in (area, "GB"))
    key = lambda k: ((k - 1) // 4, (k - 1) % 4 + 1)  # noqa: E731
    quarters = sorted(set(range(lo1, hi1 + 1)) | set(range(lo2, hi2 + 1)))
    rows = [{"quarter": qname(k), "area": release(*here_q[key(k)])["display"],
             "great_britain": release(*gb_q[key(k)])["display"]} for k in quarters]
    return result(summary, rows, m, snap, True, mass, ca1 + ca2,
                  (*bundle_notes(sic_codes), *(() if closed else (SHARE_CAVEAT,)), PICKED_CAVEAT, PARTS_NOTE,
                   *(gap_note(lo1, hi2) if closed else ())), closed, across=" across both periods")


@mcp.tool(annotations=READ_ONLY)
@coded
def compare_two_areas(
    sic_codes: list[str] = SICS_FIELD,
    area: str = Field(description="A council area, region or nation code from find_area"),
    other_area: str = Field(description="A second, non-overlapping council area, region or nation code"),
    to_quarter: TO_Q = None,
    from_quarter: FROM_Q = None,
    against: AGAINST = "year_before",
    include_closed: CLOSED_IN = True,
) -> CountResult:
    """Head to head: which of two places has more new companies in this industry, and which grew faster? Gives each
    area's count for a period (default the latest four quarters) and the earlier one, a test of whether one has more,
    and a test of whether one area's share of the two together changed (that is, one grew faster, or fell less if it
    fell). Both tests allow for rounding. Formation-agent addresses are left out."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, what = expand_sics(sic_codes)
    name_a, name_b = area_name(area), area_name(other_area)
    if set(members(area)) & set(members(other_area)):
        raise ToolError("BAD_AREA: the two areas overlap (one contains the other, or they are the same). Pick two "
                        "separate places, or compare one with Great Britain using compare_area_with_great_britain.")
    lo1, hi1, lo2, hi2 = window(from_quarter, to_quarter, against, snap)
    closed = include_closed
    (a1, ca1), (a2, ca2), (b1, cb1), (b2, cb2) = (
        total_of(sics, lo, hi, x, closed)
        for x, lo, hi in ((area, lo1, hi1), (area, lo2, hi2), (other_area, lo1, hi1), (other_area, lo2, hi2)))
    p1, p2 = span(lo1, hi1), span(lo2, hi2)
    how = (f"were registered in {p2}, including those dissolved by {snap:%-d %B %Y}" if closed else
           f"registered in {p2} were still open on {snap:%-d %B %Y}")
    summary = (f"In {name_a}{covering(area)}, {about(a2)} companies with {what} {how}, against {about(a1)} from {p1}. "
               f"In {name_b}{covering(other_area)}: {about(b2)} against {about(b1)}."
               + ("" if closed else LIVE_NOTE))
    more = change(b2, a2, cb2, ca2)  # 'increase' here means the first area has more
    # review codex-periods: the doubt sits next to the claim, so a quoted half-sentence still carries it
    step = next_step(sics, (area, other_area), lo1)
    summary += (" Too few companies to say which has more." + step if more == "too few to compare" else
                f" {cap(name_a if 'increase' in more else name_b)} likely had more in {p2}{TEST_NOTE}."
                if more.startswith("clear") else f" Neither clearly had more in {p2}, allowing for rounding.")
    faster = share_change(a1, a1 + b1, a2, a2 + b2, (ca1, ca2), (cb1, cb2))
    if faster == "too few to compare":
        summary += " Too few companies to say which grew faster." + ("" if more == "too few to compare" else step)
    else:
        ahead, x1, x2 = (name_a, a1, a2) if "rise" in faster else (name_b, b1, b2)
        moved = ("grew faster in percentage terms" if x2 > x1 else "fell less in percentage terms" if x2 < x1
                 else "held steady while the other fell")
        summary += (f" {cap(name_a)}'s share of the two together went from {a1 / (a1 + b1):.1%} to "
                    f"{a2 / (a2 + b2):.1%}" + (f", so {ahead} likely {moved}{TEST_NOTE}." if faster.startswith("clear") else
                                               ": neither clearly grew faster in percentage terms."
                                               + recent(closed, hi2, snap)))
    summary += agent_warning(sics, lo2, hi2, closed)
    rows = [{"area": n, "period": p, **(floored(release(x, c), total_of(sics, *w, place)) if closed else release(x, c))}
            for n, p, x, c, w, place in ((name_a, p1, a1, ca1, (lo1, hi1), area), (name_a, p2, a2, ca2, (lo2, hi2), area),
                                         (name_b, p1, b1, cb1, (lo1, hi1), other_area),
                                         (name_b, p2, b2, cb2, (lo2, hi2), other_area))]
    mass = sum(sum(with_closed("p_mass", closed, sics, lo, hi, x).values())
               for x in (area, other_area) for lo, hi in ((lo1, hi1), (lo2, hi2)))
    return result(summary, rows, m, snap, True, mass, ca1 + ca2 + cb1 + cb2,
                  (*bundle_notes(sic_codes), PAIR_CAVEAT, *(gap_note(lo1, hi2) if closed else ())), closed,
                  across=" across both areas and both periods")


@mcp.tool(annotations=READ_ONLY)
@coded
def rank_areas_against_great_britain(
    sic_codes: list[str] = SICS_FIELD,
    direction: Literal["growing", "shrinking"] = "growing",
    to_quarter: TO_Q = None,
    limit: int = Field(10, ge=1, le=25),
    from_quarter: FROM_Q = None,
    against: AGAINST = "year_before",
    include_closed: CLOSED_IN = True,
) -> CountResult:
    """Hotspots: in which council areas did this industry's share of Great Britain's new companies rise (or fall)
    most, in a period (default the latest four quarters) against an earlier one (see against)? Every area is tested, so the bar for "stands out" is raised
    to allow for testing hundreds of areas at once. Only areas that stand out are listed, strongest evidence first.
    Areas without at least 10 companies for certain in both periods aren't tested. Counts include companies dissolved
    since, so an area isn't made to look like a hotspot by closures in the older period. This doesn't say which area
    grew fastest: an area missing from the rows may have grown as fast on less evidence. To check one named area, use
    compare_area_with_great_britain."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, what = expand_sics(sic_codes)
    lo1, hi1, lo2, hi2 = window(from_quarter, to_quarter, against, snap)
    names = dict(db().execute("SELECT ladcd, ladnm FROM areas WHERE NOT northern_ireland "
                              "AND ladcd <> 'unmatched'").fetchall())
    closed = include_closed
    c1, c2 = (totals(sics, lo, hi, list(names), closed, "geo") for lo, hi in ((lo1, hi1), (lo2, hi2)))
    (g1, cg1), (g2, cg2) = (total_of(sics, lo, hi, "GB", closed) for lo, hi in ((lo1, hi1), (lo2, hi2)))
    f1 = with_closed("p_area", closed, sics, lo1, hi1, None, "ladcd", floor=True)
    f2 = with_closed("p_area", closed, sics, lo2, hi2, None, "ladcd", floor=True)
    h1, h2 = sum(f1.values()), sum(f2.values())
    ranked = [(code, c1[code,][0], c2[code,][0]) for code in names]
    ranked = [r for r in ranked if min(f1.get((r[0],), 0), f2.get((r[0],), 0), h1 - f1.get((r[0],), 0),
                                       h2 - f2.get((r[0],), 0)) >= 10  # at least 10 for certain, every part
              and min(r[1], r[2], g1 - r[1], g2 - r[2]) >= 10]  # and the totals tested (batch B: not the same sums)
    small, tests = len(names) - len(ranked), len(names)  # every area: which pass the gate depends on rounding
    up = direction == "growing"

    def cells(code: str) -> tuple:  # the area's cells, and the rest of GB's: GB's total less the area's, both rounded
        a1, a2 = c1[code,][1], c2[code,][1]
        return (a1, a2), (cg1 + a1, cg2 + a2)

    def cautious(code: str, x1: int, x2: int) -> float:  # allows for the most rounding could have moved the cells
        return share_z(x1, g1, x2, g2, *cells(code), True)

    def tier(code: str, x1: int, x2: int) -> int:
        v = share_change(x1, g1, x2, g2, *cells(code), tests)
        if not v.startswith("clear"):
            return 1
        return 2 if ("rise" in v) != up else 0

    # Order: evidence tier, then the z that allows for rounding, so noisy small areas don't float to the top.
    ranked = sorted(((tier(code, x1, x2), code, x1, x2) for code, x1, x2 in ranked),
                    key=lambda r: (r[0], -cautious(*r[1:]) if up else cautious(*r[1:])))
    rows = [{"area_code": code, "area_name": names[code], "earlier": release(x1)["display"],
             "latest": release(x2)["display"], "share_earlier": f"{x1 / g1:.2%}", "share_latest": f"{x2 / g2:.2%}",
             "verdict": RANK_VERDICTS[t] + (f"{'fall' if up else 'rise'} instead" if t == 2 else "")}
            for t, code, x1, x2 in ranked[:limit] if t == 0]  # only standouts: an order on chance reads as a ranking
    strong = sum(r[0] == 0 for r in ranked)
    p1, p2 = span(lo1, hi1), span(lo2, hi2)
    warn = agent_warning(sics, lo2, hi2, closed).lstrip()
    how = (f"registered in {p2}, including those dissolved by {snap:%-d %B %Y}" if closed else
           f"registered in {p2} and still open on {snap:%-d %B %Y}")
    warn += "" if closed else LIVE_NOTE
    summary = (RANK_LIMIT + (warn + " " if warn else "") + f"Companies with {what} {how}, against {p1}: "
               f"{len(ranked)} council areas had at least 10 for certain in both periods and were tested for a {'rise' if up else 'fall'} "
               f"in their share of Great Britain, with the bar raised for all {tests} areas (which pass that check depends on rounding). "
               f"Of the {len(ranked)} tested, {strong} stand{'s' if strong == 1 else ''} out on a test that allows for rounding, though rounding can still mislead it; "
               f"the rest could be chance or moved the other way, so they aren't listed. "
               + ("The rows are the areas that stand out, strongest evidence first (not size of change). " if strong else
                  "No area is listed: none can be named as a hotspot. ")
               + f"{small} areas were too small to judge, so an area that grew from a small base can't appear here."
               + ("" if strong else recent(closed, hi2, snap)))
    if not ranked:  # testing phase: no area has enough companies to tell a real change from rounding
        summary = (RANK_LIMIT + (warn + " " if warn else "") + f"Companies with {what} {how}, against {p1}: no "
                   f"council area had at least 10 for certain in both periods, so none can be tested or named as a hotspot. "
                   f"Ask about the UK total, a wider industry, or one area with compare_area_with_great_britain.")
    return result(summary, rows, m, snap, True, sum(sum(with_closed("p_mass", closed, sics, lo, hi).values())
                                                    for lo, hi in ((lo1, hi1), (lo2, hi2))),
                  cg1 + cg2, (*bundle_notes(sic_codes), RANK_CAVEAT, *(() if closed else (SHARE_CAVEAT,)),
                              *(gap_note(lo1, hi2) if closed else ())), closed,
                  across=" across every council area and both periods")


def division(s: str) -> str:
    return s[:2] if s.isdigit() else NO_ACTIVITY


def div_floors(t: str, closed: bool, sics: list[str], lo: int, hi: int, where: str | None,
               floor: bool = True) -> dict[str, int]:
    """Code-level protected sums (floors: companies for certain) added up by 2-digit division."""
    out: dict[str, int] = {}
    for (s,), n in with_closed(t, closed, sics, lo, hi, where, "sic", floor=floor).items():
        out[division(s)] = out.get(division(s), 0) + n
    return out


BREAKDOWN_CAVEAT = ("A change here may only follow the same change across Great Britain (see the great_britain "
                    "column). Each division is broad: for one activity, ask about its own codes, and to test whether "
                    "this area is outpacing Great Britain in one industry, use compare_area_with_great_britain.")


@mcp.tool(annotations=READ_ONLY)
@coded
def breakdown_by_industry(
    area: str = Field(description="'UK', a region or nation, or a council area code from find_area"),
    to_quarter: TO_Q = None,
    from_quarter: FROM_Q = None,
    against: AGAINST = "year_before",
    include_closed: CLOSED_IN = True,
) -> CountResult:
    """What's growing here? New companies in every 2-digit SIC industry division (plus no activity stated) for a
    period (default the latest four quarters) against an earlier one, with a test of each change and, for an area,
    the same test across Great Britain. Every division is tested, so the bar for a clear change is raised for testing
    them all at once. Rows are in SIC order, not by size. Counts are shown only for divisions with a clear change, and
    even those rounded counts don't reliably show which division is bigger or moved more: don't rank divisions.
    Formation-agent addresses are left out of area answers."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, _ = expand_sics([ALL])
    uk = area == "UK"
    place = "the UK" if uk else area_name(area) + covering(area)
    lo1, hi1, lo2, hi2 = window(from_quarter, to_quarter, against, snap)
    closed = include_closed
    table, one, where = ("p_uk", None, "UK") if uk else ("p_area", area, area)
    size: dict[str, int] = {}
    for s in sics:
        size[division(s)] = size.get(division(s), 0) + 1

    def by_div(t: str, where: str | None, lo: int, hi: int, floor: bool = False) -> dict[str, int]:
        return div_floors(t, closed, sics, lo, hi, where, floor)

    # Division totals (size: division -> codes it covers) for counts; floors from the code cells, as in the ranking.
    x1, x2 = (totals(sics, lo, hi, [where], closed, "ind", size) for lo, hi in ((lo1, hi1), (lo2, hi2)))
    f1, f2 = by_div(table, one, lo1, hi1, True), by_div(table, one, lo2, hi2, True)
    if not uk:
        g1, g2 = (totals(sics, lo, hi, ["GB"], closed, "ind", size) for lo, hi in ((lo1, hi1), (lo2, hi2)))
        h1, h2 = by_div("p_area", None, lo1, hi1, True), by_div("p_area", None, lo2, hi2, True)
    tests = len(size)  # the family is every division, not the ones that pass the gate
    # Outsider test: one quarter against the one before said "likely more" where the year before said "likely fewer"
    seasonal = against == "previous" and (hi2 - lo2 + 1) % 4 > 0

    def verdict(a: tuple, b: tuple, fa: int, fb: int) -> str:
        if seasonal:
            return "not tested: different times of year"
        if min(fa, fb) < 10:  # at least 10 for certain in both periods, as in the ranking
            return "too few to test"
        v = change(a[0], b[0], a[1], b[1], tests)
        return "likely rose" if "increase" in v else "likely fell" if "decrease" in v else "no clear change"

    rows = []
    for d in size:
        a, b = x1[d,], x2[d,]
        v = verdict(a, b, f1.get(d, 0), f2.get(d, 0))
        clear = v.startswith("likely")  # e2e Q6 (James chose this): clients ranked the uncertain rows' counts
        rows.append({"division": d, "industry": DIVISIONS[d], "earlier": release(*a)["display"] if clear else None,
                     "later": release(*b)["display"] if clear else None, "verdict": v,
                     **({} if uk else {"great_britain": verdict(g1[d,], g2[d,], h1.get(d, 0), h2.get(d, 0))})})
    p1, p2 = span(lo1, hi1), span(lo2, hi2)
    how = (f"were registered in {p2}, including those dissolved by {snap:%-d %B %Y}" if closed else
           f"registered in {p2} were still open on {snap:%-d %B %Y}")
    (t1, ct1), (t2, ct2) = (total_of(sics, lo, hi, where, closed, {ALL: len(sics)}) for lo, hi in ((lo1, hi1), (lo2, hi2)))

    def named(v: str) -> str:
        hits = [f"{r['industry']} ({r['division']})" for r in rows if r["verdict"] == v]
        return ", ".join(hits[:6]) + (f" and {len(hits) - 6} more (see rows)" if len(hits) > 6 else "")
    up, down = named("likely rose"), named("likely fell")
    whole = "not tested" if seasonal else change(t1, t2, ct1, ct2)
    summary = (f"In {place}, {about(t2)} companies in all industries {how}, against {about(t1)} from {p1}"
               + (f": likely {'more' if 'increase' in whole else 'fewer'}{TEST_NOTE}. " if whole.startswith("clear")
                  else ": no clear change in the total. " if whole == "no clear change" else ". "))
    if seasonal:
        summary += (f"No change is tested: these two periods are different times of year, and {SEASON}. Compare with the "
                    "same quarters a year before instead.")
    else:
        summary += (f"Of {tests - 1} industry divisions plus no activity stated, tested with the bar raised for "
                    f"testing them all at once{TEST_NOTE}: "
                    + (f"new companies likely rose in {up}" if up else "") + ("; " if up and down else "")
                    + (f"likely fell in {down}" if down else "")
                    + (". The rest show no clear change or are too few to test" if up or down else
                       "none shows a clear change, or each is too few to test")
                    + ". Rows are in SIC order, not by size, with counts only where a change is clear; even those "
                    "rounded counts don't reliably show which divisions are biggest or moved most.")
        summary += recent(closed, hi2, snap) if whole == "no clear change" else ""
    if not closed:
        summary += LIVE_NOTE
    if not uk:
        summary += agent_warning(sics, lo2, hi2, closed)
    mass = 0 if uk else sum(sum(with_closed("p_mass", closed, sics, lo, hi, area).values())
                            for lo, hi in ((lo1, hi1), (lo2, hi2)))
    return result(summary, rows, m, snap, not uk, mass, ct1 + ct2,
                  (BREAKDOWN_CAVEAT, PARTS_NOTE, *(gap_note(lo1, hi2) if closed else ())), closed,
                  across=" across both periods")


@cache
def last_quarter_held() -> int:
    """The latest quarter with cells, the part-quarter up to the snapshot included: live now needs every company."""
    return db().execute("SELECT max(year * 4 + quarter) FROM p_agg").fetchone()[0]


@mcp.tool(annotations=READ_ONLY)
@coded
def count_companies_live_now(
    sic_codes: list[str] = SICS_FIELD,
    area: str = Field(description="'UK', a region or nation, or a council area code from find_area"),
) -> CountResult:
    """How crowded is it? Count companies (private limited, PLC and LLP) with these primary SIC codes that are live
    (not dissolved) in the snapshot, whatever year they were registered. Live includes companies that don't trade.
    Rows split it into those registered before 2021 and since. Area answers leave out formation-agent postcodes."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, what = expand_sics(sic_codes)
    uk = area == "UK"
    place = "the UK" if uk else area_name(area) + covering(area)
    where = "UK" if uk else area
    # Batch B: before 2021 is its own protected table (different companies from the quarterly ones, so nothing ties
    # them); live now is it plus every quarter since, so the two rows add up exactly to the total.
    before, cb = agg("p_pre2021", sics, 0, 0, [where])[()]
    since, cs = total_of(sics, 2021 * 4 + 1, last_quarter_held(), where)
    t = release(before + since, cb + cs)
    parts = release(before, cb), release(since, cs)
    if t["range"]:  # outsider test: a total's range started below its own part's
        t["range"][0] = max(t["range"][0], sum(p["range"][0] for p in parts if p["range"]))
    lead = f"About {t['display']}" if t["count"] is not None else cap(SMALL)
    summary = (f"{lead} companies with {what} were live (not dissolved) in {place} on {snap:%-d %B %Y}, whatever "
               f"year they were registered" + (f" (likely range {t['range'][0]:,}–{t['range'][1]:,})" if t["range"]
                                                else "") + ".")
    if t["low"] and t["count"] is not None:
        summary += " This is a low or uncertain count, so treat it with caution."
    rows = [{"registered": "before 2021", **parts[0]}, {"registered": "2021 onwards", **parts[1]}]
    mass = 0
    if not uk:
        mass = sum(protected_sum("p_mass", sics, 2021 * 4 + 1, last_quarter_held(), area).values()) + db().execute(
            "SELECT coalesce(sum(protected), 0)::INTEGER FROM p_pre2021_mass WHERE sic IN (SELECT unnest(?)) "
            "AND ladcd IN (SELECT unnest(?))", [sics, list(members(area))]).fetchone()[0]
    first = (f"These are companies on the register on {snap:%-d %B %Y}, whatever year they were registered. Live "
             "means not dissolved: it includes companies that never traded or have stopped, and companies in "
             "liquidation or being struck off.")
    old = (f"About {int(m['pre2021_old_sic']):,} companies registered before 2021 (across the UK) still carry a SIC "
           "code from the old 2003 list, which doesn't match today's codes, so they aren't counted here, even under "
           "all industries.")
    since_note = ("'2021 onwards' runs to the snapshot date, so it includes the part quarter after the last complete "
                  "one and can be higher than a count that stops at that quarter.")
    return result(summary, rows, m, snap, not uk, mass, cb + cs, (*bundle_notes(sic_codes), old, since_note), first=first)


CLOSURE_NOTES = (
    "Companies House dissolves companies in weekly batches of very different sizes, so closures can jump from one "
    "quarter to the next. A year's figures are steadier but can still move with a large batch.",
    "Across all areas and industries, from 2021-Q1 to 2026-Q3 together, dissolved counts are about 0.8% short of "
    "Companies House's official figures, and the gap varies by quarter. A company restored to the register no longer "
    "shows as dissolved, which may explain it. There is no official figure to check one area or industry against.",
    "This compares the counts in one period. It doesn't show whether closures are speeding up, or what share of "
    "companies close.")
ADDRESS_NOTE = ("A closure is placed at the company's last registered address, not where it worked. In many council "
                "areas a good part of closures are at single addresses with 100 or more closures, which may be "
                "liquidators' or shared offices, so an area's closures may not all be local companies. Companies at "
                "Companies House's default address, where it moves companies whose address has failed, are left out with "
                "the formation-agent addresses.")


def with_left_out(reg: int, gone: int, sics: list[str], lo: int, hi: int) -> tuple[int, int]:
    """(registered, dissolved) in an area with each side's left-out addresses put back at Great Britain's rate for
    these codes: the two sides leave out different shares, so a close area verdict can depend on them (batch C)."""
    def rate(closures: bool) -> float:
        out = sum(protected_sum("p_mass_gone", sics, lo, hi).values()) if closures else sum(
            with_closed("p_mass", True, sics, lo, hi).values())
        kept = sum(protected_sum("p_area_gone", sics, lo, hi).values()) if closures else sum(
            with_closed("p_area", True, sics, lo, hi).values())
        return 1 + out / kept if kept else 1
    return round(reg * rate(False)), round(gone * rate(True))


@mcp.tool(annotations=READ_ONLY)
@coded
def registrations_against_closures(
    sic_codes: list[str] = SICS_FIELD,
    area: Annotated[str, Field(description="'UK', a region or nation, or a council area code from find_area")] = "UK",
    to_quarter: TO_Q = None,
    from_quarter: LIST_FROM = None,
) -> CountResult:
    """Were more companies registered or dissolved? In one place (default the UK) and period (default the latest four
    quarters), compares companies registered with companies dissolved, whatever year those were registered, and tests
    which was higher, allowing for rounding. A period under a year gets the counts but no verdict, because closures
    come in weekly batches. It can't show whether closures are speeding up. Area answers leave out formation-agent
    addresses."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, what = expand_sics(sic_codes)
    lo, hi = period(from_quarter, to_quarter, snap)
    uk = area == "UK"
    place = "the UK" if uk else area_name(area) + covering(area)
    reg, cr = total_of(sics, lo, hi, area, True)
    gone, cg = agg("p_agg_gone", sics, lo, hi, [area])[()]
    p = span(lo, hi)
    summary = (f"In {place}, {about(reg)} companies with {what} were registered in {p}, including those dissolved by "
               f"{snap:%-d %B %Y}, and {about(gone)} were dissolved in {p}, whatever year they were registered.")
    more = change(gone, reg, cg, cr)  # 'increase' here means more were registered
    out_reg = 0 if uk else sum(with_closed("p_mass", True, sics, lo, hi, area).values())
    out_gone = 0 if uk else sum(protected_sum("p_mass_gone", sics, lo, hi, area).values())

    def turns(r: int, g: int) -> bool:
        return change(g, r, cg, cr) != more

    if more == "too few to compare":
        summary += " Too few companies to say which was higher." + next_step(sics, (area,), lo)
    elif hi - lo < 3:
        summary += (" This covers under a year and closures come in weekly batches of very different sizes, so it can't "
                    "say which was higher: ask for a whole year.")
    # Outsider test: Wales left out about 46,000 dissolved companies against about 17,000 counted, so the verdict also
    # has to hold with the area's own left-out addresses put back.
    elif not uk and more.startswith("clear") and (turns(*with_left_out(reg, gone, sics, lo, hi))
                                                  or turns(reg + out_reg, gone + out_gone)):
        summary += (f" Neither was clearly higher in {p}: the answer depends on the formation-agent addresses left out, "
                    "which are a different share of each side.")
    elif more.startswith("clear"):
        summary += (f" More were likely {'registered than dissolved' if 'increase' in more else 'dissolved than registered'}"
                    f" in {p}{TEST_NOTE}.")
    else:
        summary += f" Neither was clearly higher in {p}, allowing for rounding."
    rows = [{"measure": f"registered in {p}", **floored(release(reg, cr), total_of(sics, lo, hi, area))},
            {"measure": f"dissolved in {p}", **release(gone, cg)}]
    area_text = excluded = None
    if not uk:  # each side's own figures: adding them would count a company registered and dissolved here twice
        placed = unmatched_each_side()
        area_text = (f"Area means the company's registered address, not where it works. {cap(about(out_reg))} registered "
                     f"and {about(out_gone)} dissolved companies at formation-agent addresses are left out. Of the rest, "
                     f"across all areas, periods and industries, {placed[0]}% of registered and {placed[1]}% of dissolved "
                     "companies couldn't be placed in an area.")
        excluded = Excluded(mass_postcode_companies=f"{about(out_reg)} registered, {about(out_gone)} dissolved",
                            unmatched_pct=placed[0])  # the dissolved share is in the area caveat
    first = (f"Registered means companies formed in this period, including those dissolved by {snap:%-d %B %Y}. Dissolved "
             "means companies taken off the register in this period, whatever year they were registered. Neither is a "
             "business starting or stopping: some companies never trade, and dissolution often comes months or years "
             "after a company has stopped trading.")
    old = (f"About {int(m['gone_old_sic']):,} dissolved companies still carried a SIC code from the old 2003 list, which "
           "doesn't match today's codes, so they aren't counted here, even under all industries.")
    return result(summary, rows, m, snap, not uk, 0, 0,
                  (*bundle_notes(sic_codes), *CLOSURE_NOTES, *(() if uk else (ADDRESS_NOTE,)), old, *gap_note(lo, hi)),
                  True, first, area_text, excluded)


# James, 3 Nov 2026 (user review: the ranking almost never names anyone): a plain "biggest by count" list, with
# ranges and no claim of significance, answers "where are most X startups?". Ranks come from the likely ranges, so
# places whose ranges overlap share a span and no order between them is claimed (e2e Q6: clients ranked noisy rows).
LIST_CAVEAT = ("This shows size, not growth or a hotspot test. A likely rank like 2–5 means rounding and chance could "
               "put it anywhere in that span, so don't say one row beats another when their spans overlap.")


LIST_LIMIT = Annotated[int, Field(ge=1, le=25, description="Rows to list, largest first")]


def by_size(values: dict, floors: dict, limit: int) -> tuple[list[dict], int]:
    """The largest keys with at least 10 for certain, in order of rounded count, each with its likely range and a
    likely rank from every key's likely range (best: 1 + those whose range lies wholly above; worst: those whose
    range reaches its low end). values: key -> (protected sum, cells). Returns (rows, keys left unnumbered)."""
    span = {}
    for k, (v, c) in values.items():
        r = release(v, c)
        # Unnumbered: the top of the likely range release() would give it (the hard bound, 4 per cell, made a
        # division shown under 10 over 288 cells outrank Leeds retail).
        span[k] = tuple(r["range"]) if r["range"] else (0, v + 2 * sqrt(v + CELL_VAR * c))
    # At least 10 for certain, and numbered: a total rounded on its own can show under 10 over parts that aren't.
    listed = sorted((k for k in values if floors.get(k, 0) >= 10 and release(*values[k])["count"] is not None),
                    key=lambda k: (-release(*values[k])["count"], k))
    rows = []
    for k in listed[:limit]:
        lo, hi = span[k]
        best = 1 + sum(l > hi for l, _ in span.values())
        worst = sum(h >= lo for _, h in span.values())
        rows.append({"key": k, "likely_rank": str(best) if best == worst else f"{best}–{worst}", **release(*values[k])})
    return rows, len(values) - len(listed)


@mcp.tool(annotations=READ_ONLY)
@coded
def largest_areas(
    sic_codes: list[str] = SICS_FIELD,
    level: Literal["council", "region"] = "council",
    to_quarter: TO_Q = None,
    from_quarter: LIST_FROM = None,
    include_closed: CLOSED_IN = True,
    limit: LIST_LIMIT = 10,
) -> CountResult:
    """Where are most of these companies? The council areas (or regions and nations) of Great Britain with the most
    companies registered with these codes in a period (default the latest four quarters), largest first, each with a
    likely range and a likely rank. Size, not growth: for where an industry is growing, use
    rank_areas_against_great_britain. Formation-agent addresses are left out."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, what = expand_sics(sic_codes)
    lo, hi = period(from_quarter, to_quarter, snap)
    closed = include_closed
    if level == "council":
        names = dict(db().execute("SELECT ladcd, ladnm FROM areas WHERE NOT northern_ireland "
                                  "AND ladcd <> 'unmatched'").fetchall())
    else:
        names = dict(db().execute("SELECT DISTINCT rgncd, rgnnm FROM regions").fetchall())
    values = {k: v for (k,), v in totals(sics, lo, hi, list(names), closed, "geo").items()}
    floors = {k: n for (k,), n in with_closed("p_area", closed, sics, lo, hi, None, "ladcd", floor=True).items()}
    if level == "region":
        floors = {r: sum(floors.get(c, 0) for c in members(r)) for r in names}
    found, hidden = by_size(values, floors, limit)
    live = {k: v for (k,), v in totals(sics, lo, hi, list(names), False, "geo").items()} if closed else {}
    rows = [{"likely_rank": r["likely_rank"], "area_code": r["key"], "area_name": names[r["key"]],
             **{k: v for k, v in (floored(r, live[r["key"]]) if closed else r).items() if k not in ("key", "likely_rank")}}
            for r in found]
    word = "council areas" if level == "council" else "regions and nations"
    how = (f"registered in {span(lo, hi)}, including those dissolved by {snap:%-d %B %Y}" if closed else
           f"registered in {span(lo, hi)} and still open on {snap:%-d %B %Y}")
    top = "; ".join(f"{r['area_name']}, about {r['display']} (likely rank {r['likely_rank']})" for r in rows[:3])
    summary = (f"The {word} of Great Britain with the most companies with {what} {how}"
               + (f": {top}." if rows else ": none has at least 10 for certain, so none is listed.")
               + (" Rows are in order of rounded count, each with a likely range and a likely rank; places whose "
                  "ranks overlap could be in either order (none comes before another, and a tie can't be shown), and "
                  "even a single rank is an estimate from rounded counts, not certain." if rows else "")
               + (f" {hidden} {word} had too few to number for certain and aren't listed." if hidden else "")
               + (f" Only the first {len(rows)} of {len(values) - hidden} are listed: ask for a higher limit to see more."
                  if len(values) - hidden > len(rows) else ""))
    summary += agent_warning(sics, lo, hi, closed)
    gb = total_of(sics, lo, hi, "GB", closed)
    return result(summary, rows, m, snap, True, sum(with_closed("p_mass", closed, sics, lo, hi).values()), gb[1],
                  (*bundle_notes(sic_codes), LIST_CAVEAT, PARTS_NOTE, *(gap_note(lo, hi) if closed else ())), closed)


@mcp.tool(annotations=READ_ONLY)
@coded
def largest_industries(
    area: str = Field(description="'UK', a region or nation, or a council area code from find_area"),
    to_quarter: TO_Q = None,
    from_quarter: LIST_FROM = None,
    include_closed: CLOSED_IN = True,
    limit: LIST_LIMIT = 10,
) -> CountResult:
    """Which industries are biggest here? The 2-digit SIC industry divisions (plus no activity stated) with the most
    companies registered in a place in a period (default the latest four quarters), largest first, each with a likely
    range and a likely rank. Size, not growth: for what is growing, use breakdown_by_industry. Area answers leave out
    formation-agent addresses."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, _ = expand_sics([ALL])
    uk = area == "UK"
    place = "the UK" if uk else area_name(area) + covering(area)
    lo, hi = period(from_quarter, to_quarter, snap)
    closed = include_closed
    size: dict[str, int] = {}
    for s in sics:
        size[division(s)] = size.get(division(s), 0) + 1
    where = "UK" if uk else area
    values = {k: v for (k,), v in totals(sics, lo, hi, [where], closed, "ind", size).items()}
    floors = div_floors("p_uk" if uk else "p_area", closed, sics, lo, hi, None if uk else area)
    found, hidden = by_size(values, floors, limit)
    live = {k: v for (k,), v in totals(sics, lo, hi, [where], False, "ind", size).items()} if closed else {}
    rows = [{"likely_rank": r["likely_rank"], "division": r["key"], "industry": DIVISIONS[r["key"]],
             **{k: v for k, v in (floored(r, live[r["key"]]) if closed else r).items() if k not in ("key", "likely_rank")}}
            for r in found]
    how = (f"registered in {span(lo, hi)}, including those dissolved by {snap:%-d %B %Y}" if closed else
           f"registered in {span(lo, hi)} and still open on {snap:%-d %B %Y}")
    top = "; ".join(f"{r['industry']} ({r['division']}), about {r['display']} (likely rank {r['likely_rank']})"
                    for r in rows[:3])
    summary = (f"In {place}, the industry divisions with the most companies {how}"
               + (f": {top}." if rows else ": none has at least 10 for certain, so none is listed.")
               + (" Rows are in order of rounded count, each with a likely range and a likely rank; divisions whose "
                  "ranks overlap could be in either order (none comes before another, and a tie can't be shown), and "
                  "even a single rank is an estimate from rounded counts, not certain." if rows else "")
               + (f" {hidden} division{'s' * (hidden > 1)} had too few to number for certain and aren't listed." if hidden else "")
               + (f" Only the first {len(rows)} of {len(values) - hidden} are listed: ask for a higher limit to see more."
                  if len(values) - hidden > len(rows) else ""))
    if not uk:
        summary += agent_warning(sics, lo, hi, closed)
    t = total_of(sics, lo, hi, where, closed, {ALL: len(sics)})
    mass = 0 if uk else sum(with_closed("p_mass", closed, sics, lo, hi, area).values())
    return result(summary, rows, m, snap, not uk, mass, t[1],
                  (LIST_CAVEAT, PARTS_NOTE, *(gap_note(lo, hi) if closed else ())), closed)


# scripts/check_survival_agents.py, council areas on exact counts: with agents put back, 220 of 749 clear tests changed,
# and 15-26% even under agent_warning's 20% trigger, so this isn't tied to it. No figure here: regions, custom periods and
# the list's own test weren't measured (review codex-survival.md).
AGENT_SURVIVAL = (" A clear verdict here can change when formation-agent addresses are put back, so this describes "
                  "companies at other addresses.")


def survival_verdict(cautious: float, tests: int) -> tuple[int, str]:
    """Tier and words for an odds test that allows for rounding; positive z = more early dissolutions = lower survival."""
    if abs(cautious) > z_needed(tests):
        return 0, f"{'lower' if cautious > 0 else 'higher'} survival than the rest of Great Britain {NOT_CERTAIN}"
    return 1, "could be chance among this many areas" if tests > 1 else "no clear difference from the rest of Great Britain"


@mcp.tool(annotations=READ_ONLY)
@coded
def one_year_survival(
    sic_codes: list[str] = SICS_FIELD,
    area: str = Field("UK", description="'UK' for the national rate plus the council areas that stand out, or a "
                      "council area, region or nation code from find_area to compare it with the rest of Great Britain"),
    from_quarter: str | None = Field(None, description="YYYY-Qn, from 2021-Q1; default three quarters before to_quarter"),
    to_quarter: str | None = Field(None, description="YYYY-Qn; default and latest: four quarters before the last complete one"),
    limit: int = Field(10, ge=1, le=25),
) -> CountResult:
    """Of the companies registered in the period with these primary SIC codes, what share were not dissolved within
    a year? For one area, compares it with the rest of Great Britain with a significance test; for 'UK', gives the
    national rate and lists the council areas whose rate passes a test for a difference (the bar is raised for testing
    hundreds of areas). Only quarters whose companies have all had a full year are allowed."""
    m = meta()
    snap = date.fromisoformat(m["snapshot_date"])
    sics, what = expand_sics(sic_codes)
    ly, lq = last_complete_quarter(snap)
    last = ly * 4 + lq - 4  # every company registered by then has had a full year before the snapshot
    hi = parse_quarter(to_quarter, snap) if to_quarter else last
    if hi > last:
        raise ToolError(f"OUT_OF_RANGE: survival needs a full year after registration, so to_quarter can be at most "
                        f"{qname(last)}")
    lo = parse_quarter(from_quarter, snap) if from_quarter else max(hi - 3, 2021 * 4 + 1)
    if lo > hi:
        raise ToolError("BAD_RANGE: from_quarter is after to_quarter" if to_quarter else
                        f"BAD_RANGE: survival needs a full year after registration, so from_quarter can be at most {qname(hi)}")
    period = qname(lo) if lo == hi else f"{qname(lo)} to {qname(hi)}"
    def split(places: list[str], by: str = "") -> dict:
        """(dissolved within a year, the rest, cells of each) per key; the rest is live plus closed after a year."""
        early = agg("p_agg_closed", sics, lo, hi, places, by, "under_1y")
        live = agg("p_agg", sics, lo, hi, places, by)
        later = agg("p_agg_closed", sics, lo, hi, places, by, "1y_plus")
        return {k: (early[k][0], live[k][0] + later[k][0], early[k][1], live[k][1] + later[k][1]) for k in live}

    def floors(by: str = "") -> dict:
        """The fewest companies each part can hold, summed from the code cells over every council area (gate only)."""
        early = protected_sum("p_area_closed", sics, lo, hi, None, by, "under_1y", True)
        live = protected_sum("p_area", sics, lo, hi, None, by, floor=True)
        later = protected_sum("p_area_closed", sics, lo, hi, None, by, "1y_plus", True)
        return {k: (early.get(k, 0), live.get(k, 0) + later.get(k, 0)) for k in early.keys() | live.keys() | later.keys()}

    def rate(c: int, s: int) -> str | None:
        if min(c, s) < 10:  # the < 10 rule covers both parts
            return None
        return f"{s / (c + s):.1%}" if min(c, s) >= 100 else f"{s / (c + s):.0%}"  # no false precision when small

    def with_range(c: int, s: int, n: tuple | None) -> str | None:
        """Rate plus its likely range; n = (cells dissolved within a year, cells of the rest), or None for the rest
        of Great Britain (a difference of two totals, and the count is large anyway)."""
        r = rate(c, s)
        if r is None or n is None:
            return r
        lo_r, hi_r = rate_range(c, s, *n)
        # User review: "likely 95%–95%": widen until the two ends differ. Outsider test: never coarser than the rate.
        for f in (".1%", ".2%") if min(c, s) >= 100 else (".0%", ".1%", ".2%"):
            if f"{lo_r:{f}}" != f"{hi_r:{f}}":
                return f"{r} (likely {lo_r:{f}}–{hi_r:{f}})"
        return f"{r} (likely within 0.01 points of that)"

    def line(c: int, s: int, n: tuple | None) -> dict:
        return {"registered": release(c + s)["display"], "dissolved_within_a_year": release(c)["display"],
                "survived_a_year": with_range(c, s, n) or "too few to give a rate"}

    def sentence(c: int, s: int, n: tuple | None) -> str:
        r = with_range(c, s, n)
        return f"{cap(about(c))} were dissolved within a year" + (f", so {r} weren't dissolved in their first year." if r
                                                                    else "; too few to give a survival rate."
                                                                    + next_step(sics, (area,), lo))

    if area != "UK":
        place = area_name(area)
        c, s, *here = split([area])[()]
        gc, gs, *gb = split(["GB"])[()]
        rc, rs = gc - c, gs - s  # GB's totals less this area's, each rounded on its own: both their cells
        summary = (f"In {place}{covering(area)}, {about(c + s)} companies with {what} were registered in {period}, leaving out "
                   f"formation-agent addresses. {sentence(c, s, here)} Rest of Great Britain: {rate(rc, rs) or 'too few'} "
                   f"weren't, of {about(rc + rs)}.")
        if min(c, s, rc, rs) >= 10:
            cautious = odds_z(rc, rs, c, s, (gb[0] + here[0], gb[1] + here[1], *here))
            tier, words = survival_verdict(cautious, 1)
            summary += f" {cap(place)} has {words}." + (AGENT_SURVIVAL if tier == 0 else agent_warning(sics, lo, hi, True))
        else:
            summary += " Too few companies here to compare." + ("" if rate(c, s) is None else
                                                                next_step(sics, (area,), lo))
        rows = [{"group": place, **line(c, s, here)}, {"group": "Rest of Great Britain", **line(rc, rs, None)}]
        mass = sum(with_closed("p_mass", True, sics, lo, hi, area).values())
        return result(summary, rows, m, snap, True, mass, sum(here), (*bundle_notes(sic_codes), PICKED_CAVEAT, *gap_note(lo, hi)), True)

    c, s, *uk = split(["UK"])[()]
    summary = (f"Across the UK, {about(c + s)} companies with {what} were registered in {period}. "
               f"{sentence(c, s, uk)}")
    names = dict(db().execute("SELECT ladcd, ladnm FROM areas WHERE NOT northern_ireland "
                              "AND ladcd <> 'unmatched'").fetchall())
    per_area = split(list(names), "geo")
    gc, gs, *gb = split(["GB"])[()]  # GB includes the unmatched row
    ranked = [(code, *per_area[code,][:2]) for code in names]
    lows = floors("ladcd")
    hc, hs = (sum(v[i] for v in lows.values()) for i in (0, 1))
    fl = {code: lows.get((code,), (0, 0)) for code in names}
    ranked = [r for r in ranked if min(*fl[r[0]], hc - fl[r[0]][0], hs - fl[r[0]][1]) >= 10  # 10+ for certain
              and min(r[1], r[2], gc - r[1], gs - r[2]) >= 10]  # and the totals tested (batch B: not the same sums)
    tests = len(names)  # every area: which pass the 10-for-certain gate depends on rounding (Tower Hamlets food 2021)
    scored = []
    for code, x, y in ranked:
        xc, xs = per_area[code,][2:]
        z = odds_z(gc - x, gs - y, x, y, (gb[0] + xc, gb[1] + xs, xc, xs), True)  # allows for rounding (phase C, batch B)
        tier, verdict = survival_verdict(z, tests)
        scored.append((tier, -abs(z), code, x, y, verdict))
    scored.sort()
    strong = sum(r[0] == 0 for r in scored)
    rows = [{"area_code": code, "area_name": names[code], **line(x, y, per_area[code,][2:]), "verdict": v}  # C4
            for t, _, code, x, y, v in scored[:limit] if t == 0]
    summary += (f" Great Britain without formation-agent addresses: {rate(gc, gs) or 'too few to give a rate'}."
                f" Council areas (formation-agent addresses left out): {len(ranked)} had at least 10 companies "
                f"dissolved within a year and 10 that survived, for certain, and each was compared with the rest of Great Britain, "
                f"with the bar raised for all {tests} areas (which pass that check depends on rounding). {strong} differ on a test that allows for rounding, though rounding can still mislead it."
                + (" No area passes this test, so none is listed or named as better or worse." if not strong else
                   " The rows are the areas that pass this test, strongest evidence first; the rest aren't listed.")
                + " "
                f"{len(names) - len(ranked)} areas were too small to judge.")
    if not ranked:  # testing phase: dissolved counts per area too small to tell from rounding (construction: none)
        summary = (f"Across the UK, {about(c + s)} companies with {what} were registered in {period}. "
                   f"{sentence(c, s, uk)} Great Britain without formation-agent addresses: "
                   f"{rate(gc, gs) or 'too few to give a rate'}. No council area had at least 10 companies "
                   f"dissolved within a year and 10 that survived for certain, so none can be compared or named as best or worst: at "
                   f"council level these counts are too small to tell a real difference from rounding. Ask about one "
                   f"area for its own rate, or a wider industry.")
    if strong:
        summary += AGENT_SURVIVAL
    return result(summary, rows, m, snap, False, 0, sum(uk), (*bundle_notes(sic_codes), *gap_note(lo, hi)), True)


if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s %(name)s %(levelname)s %(message)s", level=logging.INFO,
                        force=True)  # to stderr; force: the MCP library may have set up logging first
    logging.getLogger("mcp").setLevel(logging.WARNING)  # its INFO lines repeat refused input, including search text
    mcp.run()
