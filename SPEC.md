# SPEC: Market Pulse MCP

**Status:** v2, 1 Nov 2026. Revised after the stage-2 panel. Built through phases A–D on James's go-ahead (scope change, 1 Nov 2026, in `DECISIONS.md`). Not yet formally signed off by James, including the privacy wording (`DECISIONS.md`, sixth review, F4).

## Who it's for
- **Primary:** hiring managers reading James's portfolio (BA, ops, AI automation).
- **Real user (to find in week 1):** a council economic-development officer. Others: Growth Hub or chamber analysts, local data journalists, commercial property agents.
- **Fallback if nobody replies by day 7:** proxy questions taken from a published local-economy report, labelled everywhere **PROXY QUESTION, NOT A REAL USER**.

## The problem
- The answer to "which industries are starting up in my area?" is in a free 5.6M-row file, but getting it means downloading 471 MB, filtering SIC codes and postcodes, and knowing the traps.
- **The traps:**
  - The snapshot holds live companies only, so older periods under-count.
  - The registered office is not where a firm trades: formation-agent addresses hold thousands of companies.
  - Small counts swing by chance.
  - AI assistants tend to keep the number and drop the caveat.

## The headline (replaces "gap vs ONS")
**Coverage by quarter:** for each incorporation quarter from 2021 Q1, the snapshot count ÷ Companies House's own official incorporation count for that quarter (the quarterly "Incorporated companies in the UK" statistics). Both count the same unit. The result reads as a survival curve: the share of each quarter's new companies still live today.
- ONS is not compared as a level. ONS births are about 35–48% of incorporations by definition (VAT/PAYE enterprises, includes sole traders). At most, one line on whether the year-on-year direction agrees.

## What it does (v1 scope)
1. **A loader:** one pinned snapshot (date plus SHA-256) → DuckDB.
   - Load every column as text, then cast.
   - Keep only codes, dates and postcodes. No company names or address lines are kept.
   - Join the pinned ONS best-fit postcode → local authority lookup.
   - Build a summary grid: local authority × 5-digit primary SIC × quarter, with flags.
2. **Three MCP tools** (read-only):
   - `find_sic(text)` → ranked candidate codes from the official SIC 2007 list.
   - `find_area(text)` → local authority codes from the ONS lookup.
   - `count_incorporations_still_live(sic_codes[], area, from_quarter, to_quarter, group_by)`, where:
     - `area` is UK or a GB local authority code
     - quarters are `YYYY-Qn`
     - `group_by` is `none`, `quarter` or `area`
     - the server computes any `change` itself
3. **One exit for every number:** `release(n)`. When the sum of protected cells is below 10 → "under 10 (rounded)", with no comparison (was "fewer than 10" until 2 Nov 2026: testing case C7 showed it for a true 13). 10 or more → the count **rounded to the nearest 5**. Published cells (UK × SIC × quarter, area × SIC × quarter, and formation-agent counts by area × SIC × quarter) are also protected once at build time by a fixed, salted random rounding to 5 (ONS cell-key style), and the server only sums protected cells. **Guarantee:** no number or combination of calls can pin a count below 10 to one value; a build-time check fails the build otherwise. Combining overlapping tables can narrow some small counts (to 2 or more possible values), the accepted residual of the ONS method (James, 1 Nov; wording changed after review 6, awaiting James's sign-off). The range and the change test add the rounding variance (6.25 per protected cell, counted from the question's shape) with a likely range of ±2√n, also rounded, flagged "low" below 30. A change is "real" only if both counts are ≥10 and |a−b| > 2√(a+b); otherwise "no clear change".
4. **The result contract:** every result returns these fields:
   - `summary`: a sentence written by the server, which the client is told to quote word for word
   - `rows`
   - `snapshot_date` and checksum
   - ranked `caveats`, the first two marked must-quote
   - `excluded`: companies at mass-registration postcodes, and the unmatched-postcode rate
5. **The coverage chart, plus a one-page memo** answering the user's (or the proxy) question for one decision.

## Counting rules
| Rule | v1 decision |
|---|---|
| New company | Incorporated in the period and present in the snapshot |
| Company types | Headline: matched to the official release's categories (checked in hour 0–1). Tools: private limited (shares and guarantee), PLC and LLP. Shown in every answer |
| SIC | SicText_1 only. "None Supplied" and 99999 go in a visible "no activity stated" bucket. 74990 stays out of caveats until it's checked against the SIC 2007 list |
| Area | Local authority district on current boundaries, from the pinned best-fit lookup. No regions in v1 |
| Mass-registration postcodes | A postcode with 500+ snapshot rows is flagged; set the cut from the distribution at load. Area answers leave these out by default and say how many were left out. The memo shows results with and without them |
| Northern Ireland | Counted in UK totals only. No area breakdown (licence) |
| Unmatched postcodes | Labelled "unmatched", never dropped. The rate goes in every answer |
| Dormancy | Not filtered or reported in v1 |
| Snapshot | One pinned file. Answers say "still live on [date]" |

**The two must-quote caveats:**
1. "These are companies registered in this period that were still open on [date]. Companies that have since closed aren't counted, so older periods look lower than they really were."
2. "Area means the company's registered address, not where it works. [n] companies at formation-agent addresses are left out, and [x]% of addresses couldn't be placed in an area."

## Security basics
- SQL uses `?` parameters only, and `group_by` maps to fixed SQL through an allowlist.
- The server opens DuckDB read-only, with external file access off. The loader uses a separate connection.
- Inputs are validated with Pydantic and regexes. Errors return a code, never a stack trace.
- No free text from the CSV reaches the client.

## Out of scope (v1)
- Dissolved companies and API calls. *(Lifted 1 Nov for phase B, gated on a one-month test: see DECISIONS.md.)*
- Company-level lookups.
- Regions.
- Northern Ireland area breakdowns.
- A dormancy filter.
- The monthly archive job (month two).
- A lead/lag study against ONS.
- Hosting and a UI.
- Forecasts.

## Success (each one checkable)
1. **Hour-12 kill check:** for the latest complete quarter, coverage is between 90% and 102%, and no quarter is above 102%. Any quarter above 100% is investigated. If it fails: one fix attempt capped at 2 hours, then stop and switch to the Xero build.
2. **Hand check:** one count reproduced by hand from the raw CSV matches the tool exactly.
3. **Unit tests:**
   - `release()` boundaries at 9, 10, 29 and 30
   - change tests: 30 vs 20 gives "no clear change", and 120 vs 60 gives a real change
   - an SQL injection attempt is rejected, and writes are blocked
   - the fixture's injection company name never appears in output
   - every result passes the schema check
4. **End-to-end:** `claude -p` with the server attached runs 5 fixed questions, including a subtraction attempt and an "ignore the caveats" request. Every answer keeps the snapshot date and a live-only phrase, and gives no exact count below 10. Target 5/5.
5. **Robustness:** the memo states the answer with and without mass-registration postcodes, and whether the conclusion changes.
6. **Decision test:** the user (or one outsider, for a proxy) reads the memo and says what they'd do differently. Recorded word for word.
7. **10-second test:** 2 people who haven't seen the project read the README's first three lines and repeat back the question, the answer and the main caveat.
8. **Real questions:** by week 3, the user has asked 3 questions. Each is logged as answered or refused, with the reason.
9. James can explain every core line.

## Order of work (hour blocks; each block's gate must pass before the next)
| Hours | Work | Gate |
|---|---|---|
| 0–1 | Counting rules into DECISIONS.md; download the official quarterly incorporation CSV; match company categories | Categories matched, written down |
| 1–3 | Load spike: snapshot → DuckDB (ask before downloading) | Row count and load time recorded |
| 3–5 | 200-row test CSV of awkward cases with hand-counted answers; **first count query, written by Claude at James's request** | The query matches the hand counts |
| 5–9 | Quarterly coverage 2021 Q1 to the latest; a second hand check | Coverage table produced |
| 9–12 | **Kill check** and the coverage chart | 90–102% rule passes |
| 12–15 | Postcode lookup, mass-postcode flag, summary grid | Unmatched rate recorded |
| 15–19 | Three tools plus `release()` (**`release()` and the change test, written by Claude at James's request**) | Unit tests pass |
| 19–21 | Schema, injection and read-only tests; end-to-end 5 questions | 5/5 |
| 21–23 | Memo and README | 10-second test |
| 23–25 | The user's questions, plus buffer | Logged |

The area work is cut first if hours run more than 20% over.

## Ignorance register

### 0OI: known (new facts from stage 2)
- **ONS business births** [V]: 2021 364k, 2022 337k, 2023 316k, 2024 317k (the latest two are provisional). Next release 19 Nov 2026.
- **Companies House incorporations by financial year** [V]: FYE24 890,684, FYE25 801,864, FYE26 815,277. These include companies dissolved since.
- **ONS industry breakdowns** come only in 15 broad groups [V].
- **The best-fit postcode lookup** is about 22 MB under the Open Government Licence [S]. Northern Ireland postcodes are for internal use only [V], so the build leaves them out and reads Northern Ireland from the BT prefix (5 Nov 2026).
- **Formation-agent addresses** host thousands of companies each [S].

### 1OI: known unknowns
1. **Which company categories does the official quarterly release count?** Owner: Claude. Test: hour 0–1, the release's notes.
2. **What is the real snapshot load time and memory use on James's Mac?** Owner: Claude. Test: the hour 1–3 spike.
3. **Where should the mass-postcode cut sit?** Owner: James (lesson). Test: the distribution at load.
4. **Who is the user, and what is their question?** Owner: James. Test: the week-1 message to 5 officers.
5. **Which boundary year does the postcode lookup use?** Owner: Claude. Test: check it for the 2023 codes E06000063–66.

### 2OI and 3OI
These surface through the hand check, the coverage chart, the user's questions and the end-to-end transcripts.

## Risks
- **Category mismatch** makes coverage meaningless. Safeguard: match categories in hour 0–1 and investigate any quarter above 100%.
- **Hours overrun.** Safeguard: timebox each block, and cut the area work first.
- **Misleading area answers.** Safeguard: leave out mass-registration postcodes, use `release()`, and require the must-quote caveats.
- **No real user.** Fallback: proxy questions, labelled. It ships as a craft piece with the coverage chart as the finding.
