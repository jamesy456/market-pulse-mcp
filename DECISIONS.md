# Decisions

Paths under `active/` are private working files, left out of the public repo.

- 2026-11-01: Project started from the Roast Room verdict (GO WITH CONDITIONS 7.0, `opportunity-scan/sessions/2026-11-01-market-pulse/verdict.md`). Python + DuckDB + MCP Python SDK.
- 2026-11-01: Companies House REST API key created (Live app "Market Pulse MCP"); stored in `.env` only; tested with one call (HTTP 200). Not used in v1.
- 2026-11-01: **Stage 2 overturned the verdict's kill line.** "30% below ONS" had no basis: ONS births (VAT/PAYE enterprises, about 316k in 2023) are a different unit from incorporations (about 891k FYE24). New headline: coverage against Companies House's own quarterly incorporation statistics. New kill check: latest complete quarter 90–102%, no quarter above 102%. Sources: `active/research/q1-ons-vs-companies-house.md`, `active/review/`.
- 2026-11-01: Cuts for v1: `compare_areas`, the separate `trend` tool, the archive job, the dormancy filter, regions, Northern Ireland area breakdowns, the ONS lead/lag idea.
- 2026-11-01: Chair's calls on 2–2 splits: precomputed grid (local authority × primary SIC × quarter); 5-question end-to-end test.

## Hours log
| Date | Hours | Block | Notes |
|---|---|---|---|
| 2026-11-01 | 0 | Setup + spec | Not counted against the 25 h |
| 2026-11-01 | 0.5 | Hour 0–1 block (Claude) | Official CSV, categories |
| 2026-11-01 | 0.5 | Hour 1–3 block (Claude) | Load spike passed |

## Hour 0–1: official figures and category matching (1 Nov 2026)
- **Source:** "Incorporated companies in the UK: July to September 2026", published 29 Oct 2026 (gov.uk). CSV saved to `data/official/incorporated_2026Q3.csv` (45,659 bytes, sha256 782235ad…0eb697). URL: https://assets.publishing.service.gov.uk/media/6ae08fa7779378370fd809e5/Incorporated_Companies_in_the_UK_July_to_September_2026.csv
- **Format:** long table. Geography (UK, England and Wales, Scotland, Northern Ireland) × Corporate Bodies (**All Companies**, **LLPs**) × month (Apr–Sep 2026) × attribute (Incorporations, Struck off, Dissolution, Restorations, …).
- **Categories (answers 1OI Q1):** the release counts companies and LLPs only. Limited partnerships are not covered (quality and methods guide). So the snapshot side must be: every company category except LLP, limited partnerships, Scottish partnerships and overseas entities → compare with "All Companies"; LLP → compare with "LLPs". Exact CompanyCategory list is confirmed at load (hour 1–3).
- **Latest complete quarter, UK, Jul–Sep 2026:** All Companies 67,891 + 57,965 + 67,933 = **193,789**; LLPs 284 + 203 + 258 = 745. These are the kill-check denominators.
- **Restorations** are published as their own line. Restored companies reappear with their old incorporation date, which is why the ceiling is 102%, not 100%.
- **New finding (changes the headline's reach):** the new-format release only goes back to April 2026 in this file; a historic series back to April 2025 is "planned but not yet published". 2021–2025 quarters exist only in old-format releases, and the guide warns against comparing across the methods change. Decision: the kill check uses Jul–Sep 2026 only (unaffected). The coverage curve before April 2026 is built from old-format releases in hours 5–9, each marked "old method" on the chart. If the old releases don't split companies from LLPs, the curve uses their totals and says so.

## Hour 1–3: load spike (1 Nov 2026)
- **Snapshot:** `BasicCompanyDataAsOneFile-2026-11-01.zip`, 494,554,856 bytes, sha256 15457954…ce550616. Download 33 s, unzip 18 s, CSV 2,814,210,743 bytes.
- **DuckDB 2.0.0 load (6 columns, all text):** 6.9 s, **5,711,779 rows**, peak memory about 768 MB. Answers 1OI Q2: no performance problem on James's Mac. Script: `scripts/spike_load.py`.
- **Dates:** `DD/MM/YYYY`, 0 unparseable in IncorporationDate.
- **Header trap confirmed:** some column names start with a space (` CompanyNumber`).
- **28 CompanyCategory values.** Clearly not in the official "All Companies": Limited Partnership (61,162), Scottish Partnership (238), Overseas Entity (30,166); LLP (49,867) compares with "LLPs". **Open for James (lesson):** whether Charitable Incorporated Organisations (40,988 + 8,033 Scottish), Registered Societies (10,770) and Industrial and Provident Societies (159) sit inside "All Companies". Test: compute Jul–Sep 2026 coverage with and without them; the version nearer 100% tells us, and both get written down.
- **Statuses:** all live (Active 5.18M, Active - Proposal to Strike off 417k, Liquidation 108k, …). No dissolved rows, as expected.

## 1 Nov 2026: lesson 1 query and the first real Q3 2026 count
- James asked Claude to write `sql/first_count.sql` instead of writing it himself. The query passes all 6 fixture checks.
- Real snapshot, 2026 Q3, company types (excluding LLPs, LPs and overseas entities): private limited 188,488, CIC 2,744, guarantee 2,049 + 175, unlimited 76, PLC 53. **Total 193,585 against the official 193,789, giving 99.9% coverage.**
- Adding CIOs (902 + 199 Scottish) gives 194,686, or 100.5%. A live-only snapshot should not be above 100%, so CIOs are **probably not** in "All Companies". Not yet confirmed from the release notes.
- LLPs: 745 in the snapshot against 745 official, which is 100.0%.
- Not yet counted: Registered Society 65, Other company type 73, ICVC under 10, Royal Charter under 10. They don't move the result.

## 1 Nov 2026: hours 5–9, quarterly coverage from 2021 Q1 (gate passed)
- **Old-method source:** `Incorporated_companies_in_the_UK_January_to_March_2026.csv` (gov.uk, 545,269 bytes, sha256 881ef7e9…d3b093). It gives quarterly figures from 2012 Q2 to 2026 Q1, with "All companies" and LLPs listed separately. 2026 Q2–Q3 come from the new-method file, with the months summed into quarters.
- **Script:** `scripts/coverage.py` reuses James's lesson-1 query, takes 3.5 s, and writes `active/coverage/coverage.csv`. Company types are the six matched on 1 Nov; charities are excluded.
- **Result (companies):**
  - 2021: 36–37%
  - 2022: 37–40%
  - 2023: 43%
  - 2024 Q1–Q4: 46 → 64%
  - 2025 Q1–Q4: 67 → 95%
  - 2026 Q1–Q3: 97.4%, 98.9%, 99.9%
- No quarter is above 100%. LLPs follow the same shape, a little higher (48% in 2021, 100% in 2026 Q3).
- **Methods change:** 2026 Q1 (old method, 97.4%) to Q2 (new method, 98.9%) shows no visible step. Each quarter is still labelled with its method.
- **Second hand check (SPEC success 2):** `scripts/hand_check.py` counts 2023 Q2 companies with plain Python csv and no DuckDB. It gets 91,131 against 91,131 from the query: a MATCH.
- **Found:** the snapshot has one blank line at line 3,010,663, probably where the 7 parts were joined. DuckDB skips it, the hand check skips it explicitly, and all 5,711,779 data rows have 55 columns.
- **Kill check preview:** the latest complete quarter is 2026 Q3, at 99.9%, inside the 90–102% range. The formal check and the chart come in hours 9–12.
- **Hours:** about 0.75 h on this block.

## 1 Nov 2026: hours 9–12, kill check PASSED
- **KILL CHECK PASS:** the latest complete quarter, 2026 Q3, is at 99.9% (rule: 90–102%), and no quarter is above 102% (the highest is the LLPs' 100.0%). The Xero fallback is not triggered, so we carry on to hours 12–15.
- The check is now runnable: `scripts/coverage.py` exits 0 on PASS and 1 on FAIL, so it re-runs against every new snapshot.
- **Chart:** `scripts/chart.py` writes `active/coverage/coverage_chart.html`. It uses no new dependencies (matplotlib is not installed and wasn't added): inline SVG, light and dark mode, a hover tooltip, a table view and a marker for the methods change. Both modes were screenshotted. The hover was not tested interactively (headless screenshot only).
- **Open question for the memo:** coverage drops steeply between companies about 1 and 2 years old (2025 Q3 at 91% → 2024 Q3 at 59%), then flattens at about 37–43% for 2021–2023. Likely cause: first-year companies that never file get struck off [U, unchecked]. Test it later with the official "Struck off" counts, if the user's question needs it.

## 1 Nov 2026: hours 12–15, postcode lookup loaded; mass-postcode findings
- **Lookup:** `PCD_OA21_LSOA21_MSOA21_LAD_AUG26_UK_LU.zip` (ONS, August 2026 edition, arcgis.com item 70be1092…, 23,559,718 bytes, sha256 3b057c94…3b3928). It has 2,729,090 postcodes and 363 local authorities. Retired postcodes keep their area code, so they are joined too.
- **Postcode tidy:** upper-case, then remove everything except letters and digits. Join on the lookup's `pcds` with spaces removed.
- **Match result (all 5.71M companies):**
  - matched to a live postcode: 97.13%
  - matched to a retired postcode: 1.00%
  - blank: 1.61%
  - not found: 0.27%, mostly overseas addresses (British Virgin Islands 3.5k, Gibraltar 637, US zip codes)
  - Channel Islands and Isle of Man: 88
  - **Unmatched total: 1.9%.**
- **Mass postcodes are much bigger than the SPEC assumed.** 592 postcodes with 500+ companies hold 16.8% of all companies and **23.9% of 2026 Q3 registrations**. The top one, in Camden, holds 89,013.
- **2026 Q3 share at 500+ postcodes, by area:**
  - Camden 91%, Islington 88%, Hackney 87%, West Suffolk 90%, Herefordshire 63%, Cardiff 43%, Manchester 35%
  - Leeds 5%, Sheffield 4%, Bristol 4%, Birmingham 9%
  - A raw count for Camden or West Suffolk is mostly formation-agent addresses. Most big-city counts outside London are mostly clean.
- **Effect of the cut-off on 2026 Q3:** a 200 cut excludes 30.5%, 500 excludes 23.9%, 1,000 excludes 20.5%, and 2,000 excludes 17.9%.
- **The cut-off is James's decision** (ignorance register, 1OI Q3), pending.
- **Cut-off decided (James, 1 Nov):** 500+ companies per postcode (SPEC default). The count covers every company at the postcode, all types and all years.

## 1 Nov 2026: hours 12–15, summary grid built (gate passed)
- **Script:** `scripts/build_grid.py` runs in 7 s and writes `data/grid.duckdb` (9 MB, gitignored).
  - Table `grid`: ladcd, ladnm, northern_ireland, sic, type_group, year, quarter, mass_postcode, companies.
  - Table `meta`: snapshot date and sha256, lookup file, cut-off, unmatched %.
  - It keeps only codes, dates and counts.
- **Coverage of the grid:**
  - From 2021, private limited (shares and guarantee), PLC and LLP: 2,721,634 companies, 945,657 cells, 361 areas plus "unmatched", 731 SIC values.
  - SIC is the first 5 characters of SicText_1. "None Supplied" and 99999 both become `none`.
  - CICs and other types are left out, per the SPEC tool types.
- **Unmatched rate inside the grid: 0.08%.** The 1.9% across the whole snapshot is mostly older and overseas companies.
- **Gate checks:**
  - **Hand check:** Leeds, 2026 Q3, private limited, non-mass. Plain csv gives 1,913, the grid gives 1,913: a MATCH (`scripts/hand_check_area.py`).
  - **Totals:** 2026 Q3 private limited 190,712, PLC 53 and LLP 745, all equal to the coverage counts.
  - **Northern Ireland:** 11 councils, flagged `northern_ireland`.
  - **Read-only:** opening read-only blocks CREATE TABLE.
- **Hours:** about 1 h on this block. Total about 4 h of the 25 h cap.

## 1 Nov 2026: hours 15–19, the three tools and release() (gate passed)
- James asked Claude to write `release()` and the change test (`src/release.py`) instead of writing them himself.
- **SDK:** the official `mcp` 2.3.0 (`MCPServer`, the v2 name for FastMCP), checked against the installed source. Dependencies are pinned in `pyproject.toml`; pytest 9.2.0 is for development only.
- **Server:** `src/server.py`.
  - **Tools:** `find_sic`, `find_area` and `count_incorporations_still_live`, all marked read-only.
  - **DuckDB:** opened `read_only` with `enable_external_access` off.
  - **Inputs:** checked with regexes plus `Literal` and `Field` limits. `group_by` picks a fixed SQL fragment. Every value goes through `?` parameters.
  - **Errors:** a code plus a message, never a stack trace.
- **SIC descriptions** come from the snapshot's own SicText strings: 730 codes in table `sic`, so there was nothing new to download.
- **Subtraction guard:** if any row in a breakdown is "fewer than 10", the total becomes "about N" (rounded to 10).
- **Change verdict:** with group_by=quarter, the first quarter is compared with the last.
- **Wording:** an area breakdown says "local authorities in Great Britain", not "the UK", because Northern Ireland and mass postcodes are out.
- **Tests:** `pytest`, 16 passing. They cover:
  - release() at 9, 10, 29 and 30, and the change cases 30 vs 20 and 120 vs 60
  - 7 bad inputs, including SQL injection in every field, a Northern Ireland area and out-of-range quarters, each rejected with no stack trace
  - writes and file reads blocked
  - no names in the grid (the fixture's injection name can't be reached)
  - the result schema, and must-quote caveats on every result
  - no exact count below 10
- **Stdio:** verified by launching the server as a subprocess with the SDK client.
- **Not yet:** an independent review, and the end-to-end `claude -p` test (hours 19–21).
- **Hours:** about 1.5 h on this block. Total about 5.5 h.

## 1 Nov 2026: independent review of f7a45a3, verdict FAIL, all 8 findings fixed
- **Reviewer:** a fresh general-purpose agent with no builder context. It proved four leak routes with live calls.
- **Blocking:**
  1. Two calls differing by one SIC code gave an exact count of 1.
  2. The range on a blurred total gave back the exact total.
  3. `excluded.mass_postcode_companies` showed exact numbers from 1 to 9.
- **Major:**
  4. Missing rows meant exactly 0.
  5. An unknown area code returned "in None".
  6. Unmatched postcodes were dropped from area breakdowns.
- **Minor:**
  7. Regexes accepted Unicode digits and trailing newlines.
  8. A "1 row hidden" note appeared on results with no rows.
- **James's decision:** every published count is rounded to the nearest 5 (the ONS approach). SPEC updated. The change verdict still uses raw counts, server side only.
- **Fixes:**
  - `release()` rounds counts and ranges to 5.
  - The mass count goes through `release()`.
  - Every quarter and every GB area gets a row, with zeros shown as "fewer than 10".
  - Unknown area codes return BAD_AREA.
  - "unmatched" is a labelled row.
  - The regexes use `re.ASCII` and `fullmatch`.
  - The hidden-row note counts only real rows.
  - The "about N" special case is gone, because rounding replaces it.
- **Tests:** 27 pass, including one regression test per finding using the reviewer's own examples. A fresh re-review follows.

## 1 Nov 2026: second independent review of 93c05e7, verdict FAIL, all findings fixed
- **B1 (blocking):**
  - **The leak:** the range was built from the raw n, so a (count, range) pair pinned n exactly for 24% of values. Two overlapping answers together pinned a hidden count below 10 (the example was removed before publishing).
  - **Fix:** the range and the "low" flag now use only the rounded count. A test checks that every n from 10 to 4,999 in the same bucket gives the same output.
  - "Low" now means a *published* count below 30, so n=28–29 shows 30 and isn't flagged.
- **M1:** the "no activity stated" bucket couldn't be reached. Fix: `sic_codes` accepts `none`, and `find_sic` lists it for "none", "no activity", "dormant" and 99999.
- **m1:** UK totals showed mass postcodes as "fewer than 10 left out". They now say "none (UK totals include them)".
- **Note, also fixed:** `_` was a LIKE wildcard in find_sic and find_area. It is no longer allowed.
- **Tests:** 32 pass. A third fresh review follows.

## 1 Nov 2026: third independent review of f6d8e4c, verdict FAIL, fixed with cell-key protection
- **B1:**
  - **The attack:** per-answer rounding gives each call a fresh rounding error. Calling `[t, p]` and `[p]` over hundreds of partner codes p averages that error away. With 800 calls, the reviewer recovered six "fewer than 10" UK counts exactly.
  - **James's decision:** protect each stored cell (the ONS approach) rather than accept it as a known limit.
- **Fix:**
  - `build_grid.py` adds `protected`: each cell is randomly rounded to a multiple of 5, rounding up with probability (count mod 5)/5. The direction comes from `md5_number(salt | cell key)`.
  - The salt is a secret `MARKET_PULSE_CELL_KEY_SALT` in `.env` (64 hex characters, generated locally, gitignored, never printed). Without it, the rounding direction can't be predicted.
  - The server sums only `protected`, and a test checks this. `companies` stays for the hand checks.
- **Effect:**
  - Unbiased: 2,721,820 protected against 2,721,634 raw, and cells with a true count of 1–9 average within 0.03 of their true value.
  - Typical extra noise, measured: UK cleaning, one quarter ±37 (2.8%); Leeds cleaning 2021–26 ±10; UK all industries, one quarter ±479 (0.3%). That is about half the likely range we already show.
  - The Leeds hand check still MATCHES at grid level (1,913).
- **Minor fixes from the same review:**
  - The summary says "no activity stated" instead of "SIC none".
  - The area-breakdown summary says it excludes formation-agent addresses.
- **Tests:** 34 pass, including the reviewer's attack run over 40 partners: the difference is always the same multiple of 5.

## 1 Nov 2026: fourth independent review of b84a652, verdict PASS WITH FIXES, fixed
- **Privacy and security rules 2–6: all PASS.** The rounding is unbiased (round-up rates 0.200/0.400/0.600/0.801), can't be predicted without the salt, and the salt is not in git.
- **F1 (blocking, correctness):**
  - **The problem:** protecting the fine grid (type × mass flag) meant one UK answer summed about 86 noisy cells. 24.7% of likely ranges missed the raw count, and 31% of year-on-year change verdicts flipped.
  - **Fix:**
    - Protect at the level the tools read: `p_uk` (SIC × quarter), `p_area` (GB area + unmatched × SIC × quarter, mass excluded) and `p_mass`, plus `areas` for names. The server never reads `grid`, and a test checks this.
    - The range and the change test add 6.25 variance per protected cell, counted from the question's shape (codes × quarters × areas), never from the data.
  - **Re-measured on all 10,789 UK cells with raw ≥10:** 0% fall outside the released range. Change verdicts against raw: 6.9% differ, mostly at the 10 threshold ("too few" vs "no clear change", 522) or more cautious ("no clear change" for a raw real change, 224). Wrongly claimed changes: 1.1%.
- **F2:** a non-must caveat now says small counts are approximate (a 10 could really be 3). The range also allows for it.
- **F3:** unexpected failures return `INTERNAL`, with no internals. Pydantic input-validation errors still come from the SDK without our code prefix (no traceback). Accepted.
- **F4:** duplicate SIC codes are counted once.
- **Tests:** 38 pass. A fifth fresh review follows.

## 1 Nov 2026: fifth independent review of deafc7e, verdict PASS WITH FIXES, fixed
- **Passed:** release/change, privacy (0 cells pinned on the real grid), SQL safety, result contract, counting rules. Range misses: 0% for single cells, 0.03–0.10% for multi-cell shapes. Change verdicts never flip direction.
- **F1 (medium, privacy for future rebuilds):** `p_uk` is rounded separately from the area and mass cells it overlaps, so a rebuild could let a client pin a small cell (for example, UK shows 0 and four cells show 5, so each must be exactly 1).
  - **Tried the reviewer's fuller fix and rejected it, with measurements.** Making `p_uk` the sum of the area cells brings back review 4's accuracy problem. Adding a protected GB table for F2 doubled the cells a client could narrow (2,570 → 5,240) and revealed that some zero cells are non-zero.
  - **Fix:** `scripts/pin_check.py` runs inside `build_grid.py`. It works out every bound a client could derive by combining `p_uk` with the area and mass cells, and the build deletes the grid and fails if any cell below 10 is pinned to one value.
  - **Current grid:** 0 pinned. 2,570 small cells can be narrowed but not pinned (tightest: two possible values, 9 cells). Accepted as the known residual of independently rounded overlapping tables, as with ONS cell-key tables.
- **F2 (medium, accuracy):** the total for an area breakdown sums about 351 mostly empty cells per code and quarter, so its honest range was useless (for example "About 20 (0–115)"). The summary now leaves the range out for that shape and points to the UK question, which reads one cell.
- **F3 (low):** `find_sic` and `find_area` are wrapped in `@coded`.
- **F4 (low):** the caveat now says a 10 could really be as low as 2 (two cells of 1, each rounded up).
- **Tests:** 43 pass, with one regression test per finding (the pin check runs against the live grid). The Leeds hand check was rerun after the rebuild.

## 1 Nov 2026: sixth independent review of 41eedd3, verdict PASS WITH FIXES (all low or doc), fixed
- **Threat model confirmed complete for one build.** The tables make one linear constraint per code and quarter (area + mass + NI = UK, NI ≥ 0), and one pass of propagation is exact. Quarters, SIC lists, the unmatched row and the `p_mass` caveat add nothing.
- **F1:** `pin_check` now also logs UK cells narrowed by their parts. Narrowed but not pinned: 3,739 (previously logged as 2,570, which counted area and mass cells only). Pinned: 0. The NI remainder always spans 9+ values, so it is never pinned.
- **F2: rules for rebuilds (the month-two archive job).**
  - The salt `MARKET_PULSE_CELL_KEY_SALT` stays fixed for good. Rotating it lets a client intersect two independent roundings of the same cell.
  - Before more than one grid version is ever served, `pin_check` must be extended to check across versions.
- **F3: if the pin check fails, there's no automatic recovery.** Never rotate the salt until it passes, because that is salt-shopping. Stop, log the pinned key, and ask James. The likely fix is merging that code into its 4-digit class.
- **F4: SPEC wording changed to the real guarantee.** No combination of calls can pin a count below 10 to one value. Some small counts can be narrowed to 2 or more possible values. **Awaiting James's sign-off.**
- **No seventh review:** these changes touch only logging and documentation, and every tool path is unchanged. The `handover-checklist` and `security-checklist` gates will review them.

## 1 Nov 2026: hours 19–21 end-to-end test (SPEC success 4), gate PASSED 5/5
- **Setup (`scripts/e2e.py`):**
  - The client is `claude -p` with Sonnet 5.5. Only the market-pulse server is attached, with no built-in tools and no settings.
  - 5 fixed questions, including a subtraction attempt (sugar cane), "ignore the caveats" (Manchester vape shops), the formation-agent trap (Hackney) and the survivorship trap (restaurants, 2021 vs 2025).
- **Checks per answer:**
  - the snapshot date
  - a live-only phrase
  - no exact count below 10
  - every quoted server summary matches one the server actually returned (added after the first run)
- **First real run:** every answer kept the caveats, and the client refused the subtraction and the caveat removal.
  - **Q5 invented a quote:** "Fewer than 10" restaurants from 2021, when the server said about 2,390. Reproduced directly and in a fully recorded rerun, the server returned 2,390 both times, so the slip was the client's.
  - **Response:**
    - The harness now records every tool call and result, adds the matching-quote check, and runs each question 3 times.
    - James's rule: if the client slips again, change the server to give it less room. For example, give the headline number its own field and word the instruction more firmly.
- **3-round result: 15/15 answers pass, so 5/5 questions pass.**
  - Every answer quotes at least one real server summary, and all three Q5 answers give 2,390 and 8,105. The server fix was not needed.
  - **Observed slip rate:** 1 invented quote in 20 client answers so far. It is the main known residual, and the README and memo will say so. Cost: about $0.27 for the 15 runs.
- **Harness fixes along the way:**
  - `claude -p` needed James to run `claude auth login`.
  - The small-number check had flagged the "1" in "1 November".
  - Client errors had been recorded as empty answers.

## 1 Nov 2026: hours 21–23, memo and README
- **Proxy question (no officer has replied yet):** the source is Leeds City Council's Economic Vision ([24 Oct 2025](https://news.leeds.gov.uk/news/multibillion-economic-vision-for-leeds-to-drive-creation-of-100-000-jobs)), which names Digital & Tech a priority sector. Decision: should start-up support in Leeds favour digital founders? It is labelled PROXY everywhere and will be redone if a real officer asks.
- **Method:**
  - Digital means 7 SIC codes (62011, 62012, 62020, 62090, 63110, 63120, 58290).
  - Compare the last 4 complete quarters (Q4 2025 – Q3 2026) with the 4 before. Use **Leeds's share of GB**, not raw growth, because survivorship inflates raw growth on both sides.
  - Every figure comes from the server's own released output.
- **Result:**
  - **Agent addresses left out:** Leeds 370 → 535 (+45%), GB 25,135 → 38,075 (+51%). Share 1.47% → 1.41%: **no clear change**.
  - **Agent addresses included:** share 1.02% → 0.88%, first reported as a clear fall. **That was wrong; see the memo review below.**
- **README:** the first 3 lines are the question, the answer and the main caveat, ready for the 10-second test. It is non-technical, with run steps and error behaviour for whoever runs it.
- **Handover fix found while writing the README:** `@coded` discarded unexpected errors without logging them. It now logs to stderr (the client's MCP log) and never into the answer. Test added; 44 pass.
- **Still needed from people (James):**
  - the 10-second test (2 people who haven't seen the project read the README's first 3 lines)
  - the decision test (one outsider reads the memo and says what they'd do differently, recorded word for word)

## 1 Nov 2026: fresh review of the memo and README (4b0368a), verdict FAIL, fixed
- **Blocking: my share test was wrong.**
  - My test compared only the newer year's Leeds count with an expected value. It treated the older share as exact and left out the rounding noise in the older year and in GB.
  - **Correct method (`scripts/memo_numbers.py`):** the log odds ratio of Leeds against the rest of GB, using Poisson variance plus 6.25 per protected cell summed (7 codes × 4 quarters per area; GB uses every area). |z| > 2 counts as clear, the same rule as `release.change()`.
  - **Results:**
    - Agent addresses left out: z = −0.58.
    - Agent addresses included (GB area plus GB agent cells as the denominator, so Northern Ireland is out): 1.03% → 0.90%, z = −1.64.
  - **Both are no clear change, so the conclusion does NOT flip** (SPEC success 5). The memo's robustness section is rewritten to say this.
- **Medium:**
  - The memo now labels "closures shrink both at the same rate" as an assumption.
  - It cites official all-industry figures, which fell 818,153 → 775,576 (−5%), while the snapshot holds 76% of the older year and 98% of the latest. So a large part of the +45% is closures (corrected by the re-review below).
  - Both share rows now use GB denominators.
  - The GB row is labelled approximate, because breakdown totals carry no range.
- **Low:**
  - The README's test count is now 44.
  - "Agent addresses elsewhere" now says "across Great Britain".
  - The headline reads "no sign Leeds is pulling ahead", not "keeping pace".
- **Learning:** the memo's statistics needed the same independent review as the code. One number I worked out by hand was wrong, and the reviewer recomputed it. Every memo number now comes from one script.

## 1 Nov 2026: re-review of 64b6331, verdict PASS WITH FIXES, fixed
- **The re-review confirmed** every memo number against `memo_numbers.py`, the official totals, the cell counts, and the z values: −0.58 and −1.64 with rounding allowed, −0.69 and −2.17 without.
- **High:** "almost all of the +45% is closures" overclaimed.
  - All-industry snapshot counts rose 21% while official figures fell 5%, so survivorship inflates growth by ×1.28.
  - Adjusted real rise: Leeds digital +13%, GB +19%, assuming digital closes at the all-industry rate. Now computed in the script.
  - The memo says "a large part".
- **Medium:** 6.25 per cell is the most rounding can add, so z = −1.64 understates the size of the change.
  - The verdict with agent addresses included is now "borderline: a small fall that may be real".
  - The script prints both bounds.
  - The headline is unchanged: neither a flat share nor a fall is "pulling ahead".
- **Low:**
  - A footnote on the official method change at 2026-Q2.
  - "Companies, excluding LLPs" is now stated.
  - The README answer uses the memo's wording.
  - "Within noise" is now "too small to be sure it's real".
  - The approximate GB row now says why.

## 1 Nov 2026: scope change approved by James, a more comprehensive MCP (phases A–D)
- **Why:** the benchmark showed that an AI with web search, or with an existing Companies House API MCP (this log calls the three tried MCP A, B and C: James chose on 5 Nov 2026 not to name them), can count companies. Including closed companies, which v1 can't. Market Pulse needs a decisive reason to exist: it **measures markets**, where those tools find companies.
- **Novelty check:**
  - GitHub, 9 queries in all: company-lookup MCPs exist; none do market aggregates. 4 queries for survival or closure analysis on Companies House data found nothing.
  - The official alternative is ONS Business Demography survival rates: annual, 15 broad industry groups only.
- **Plan (Codex agreed and reordered; its critique is in `active/review/codex-ideas.md`):**
  - **A (no key):**
    - industry groups (SIC prefixes)
    - a national comparison (share of GB, location quotient, share-change test)
    - hotspot ranking (minimum counts, correction for multiple testing)
    - a one-call area brief
  - **B (free API key):** a closed-company backfill, gated on a one-month test against the official totals. Then survival and closure tools.
  - **C:** a harder benchmark against an AI using MCP A, on Codex's demo question.
  - **D:** the Codex review fixes, the handover and security gates, then GitHub (ask before pushing).
- **SPEC v1 "out of scope: dissolved companies and API calls" is lifted for B only.** This is an estimated 11 h more, about 20 of the 25 h cap.

## 1 Nov 2026: phase A built (no API key needed)
- **Industry groups:** `sic_codes` accepts 2–4 digit prefixes (for example "812" expands to all 7 cleaning codes). `find_sic` also returns the 3-digit groups of its matches, and every summary lists the codes used. The server instructions tell the client to name them.
  - **Why:** in the benchmark, "cleaning" was a rise on 81210 alone (17 → 20) and a fall on the whole group (39 → 29).
- **`compare_area_with_great_britain`, the one-call area brief:**
  - the latest 4 quarters against the 4 before, for the area and for GB (formation-agent addresses left out on both sides)
  - the share change, with a verdict
  - the location quotient
  - an 8-quarter trend
  - It reproduces MEMO.md's 1.47% → 1.41% "no clear change" in one call (test).
- **`rank_areas_against_great_britain`, hotspots:**
  - **Who gets ranked:** every GB council area with at least 10 companies in both years.
  - **The test:** each area's share change is tested at a Bonferroni-corrected threshold (204 areas tested means z > 3.6).
  - **The verdicts:** "stands out", "possible, but could be chance among this many areas", or "no clear difference".
  - **Example:** cleaning in Bradford went 40 → 90 but doesn't stand out after testing 204 areas. A naive ranking would have called it a hotspot.
- **One shared test:** `release.share_change` / `share_z`, used by both tools and by `scripts/memo_numbers.py`.
  - The cautious z adds up to 6.25 rounding variance per protected cell; the bold z adds none.
  - **Verdicts:** clears the bar on the cautious z → "real"; only on the bold z → "possible (borderline)".
- **Privacy:**
  - Every new number is a sum of protected cells: multiples of 5, the same values `release()` shows.
  - Shares are shown only when both counts are at least 10.
  - Ranking order comes from protected sums only.
  - No new table is read.
- **Speed:** all three new calls take 0.1 s together. **Tests:** 55 pass (11 new).

## 1 Nov 2026: phase A review fixes (fresh reviewer: PASS WITH FIXES, no leak, no correctness bug)
- **Ranking verdicts, three tiers:** "stands out, even allowing for rounding" (cautious z clears the corrected bar), "stands out unless rounding moved it unusually" (only the bold z does) and "could be chance among this many areas".
  - **Why:** the worst-case rounding allowance (6.25 per cell) meant the top tier almost never fired, so the old labels hid every signal. The summary counts each tier, so zero in the top tier doesn't read as "no hotspots".
- **Order:** tier first, then bold z. Before, "possible" rows could sit below "no clear difference" rows.
- **Direction:** a move against the asked direction is always "could be chance", never a standout.
- **Rest of GB** now gets `cells_gb − cells_a` rounding cells (it counted the area's cells twice).
- **Selection bias:** `compare_area_with_great_britain` says in its description and caveats that an area picked from the ranking should be quoted with the ranking's verdict. The single-area test is too lenient after picking the top of 200+.
- **Summary** says that areas growing from under 10 can't appear, and that rows are ordered by strength of evidence, not size of change.
- **Small fixes:**
  - The `protected_sum` guard is now `if/raise`, so it survives `python -O`.
  - A code given both alone and inside its group is listed once.
- **The release unit is the protected cell (SIC × area × quarter), not the year.** Sums and differences of released cells are allowed: they reveal nothing beyond the cells themselves, which `release()` would show anyway.
- **Tests:** 58 pass (3 new, 1 tightened).
- **Re-review (fresh reviewer: PASS WITH FIXES, no leak), all applied:**
  - **Rest-of-GB fix in the compare tool too.** My first fix only covered the ranking tool, though this file said both.
  - **New label, "clear fall/rise instead":** an area that clearly moved against the asked direction now gets this, not "could be chance".
  - **Middle tier renamed** "likely stands out (rounding could explain it)".
  - **The summary** says "Of the N tested", so its counts aren't read as describing only the rows shown, and it uses singular verbs where they fit.
  - **Nested groups** (["81","812"]) are labelled once.
  - **`tier()`** is computed once per area.

## 1 Nov 2026: phase B gate PASSED (live snapshot + closed companies = official totals)
- **The check:** `scripts/closed_check.py <quarter>` counts closed companies by type and status with the advanced search API (24 requests per quarter, hit counts only) and adds them to the snapshot count.

  | Quarter | Snapshot | Closed (API) | Sum | Official | Gap |
  |---|---|---|---|---|---|
  | 2021-Q1 | 76,267 | 135,065 | 211,332 | 211,368 | −36 |
  | 2024-Q4 | 115,822 | 65,436 | 181,258 | 181,261 | −3 |
  | 2026-Q2 (new method) | 190,146 | 2,139 | 192,285 | 192,287 | −2 |

- **What this means:** within 0.02% on both counting methods, so the API's closed companies fill the survivorship gap. All of them have status "dissolved"; the other closed statuses returned 0.
- **Next:** the full backfill of closed companies' SIC, postcode and dates, protected exactly like the live grid, then the survival and closure tools.

## 2 Nov 2026: Codex review of the tests and the phase B gate (PASS WITH FIXES)
- **Type mapping (high):** checked at company level by retrieving one day (15 Oct 2024) of dissolved companies.
  - 1,051 of 1,051 hits were retrieved, with no duplicate company numbers.
  - Every type is in the gate's list, or is an LLP, which is correctly left out.
  - CICs appear under guarantee types, which are already counted.
- **Paging (high):** this applies to the backfill, not the gate. The backfill will fetch one day at a time (about 1,000–1,500 records, under the 5,000 page size), assert retrieved = hits for each day, and dedupe by company number. Paging past 5,000 also works (HTTP 200).
- **404 as zero (medium), fixed.** Only a bodiless 404 counts as "no results". A bad type or status returns a 400, which already raises an error.
- **Vacuous test (medium), fixed.** The ranking test now asserts the top row is a standout, so the direction check always runs.
- **LQ divide by zero (medium), rejected.** GB includes the area, so `gb_all ≥ here_all ≥ 10`, and `g2 ≥ a2 ≥ 10` is guarded.
- Codex couldn't run pytest in its read-only sandbox. 58 pass here.

## 2 Nov 2026: closed-company backfill (phase B), with two Codex reviews before collecting the data
- **`scripts/backfill_closed.py`:**
  - Fetches one incorporation day at a time, 2021-01-01 to 2026-10-31, `company_status=dissolved` only (the gate found no other closed status).
  - Paced at 0.55 s, under 600 requests per 5 minutes. Retries on 429 and 5xx.
  - Stops if retrieved ≠ hits, a company number repeats, or a cessation date doesn't parse.
  - Keeps every company type, so nothing is dropped at download.
  - Writes atomically, one file per day plus a manifest, so it can resume.
- **`scripts/backfill_check.py`:**
  - Stops if any day or quarter is missing, a coverage row is missing or doubled, a date is null, or a company number repeats across files.
  - Reports every type outside the gate's list.
  - Fails any quarter more than 0.03% off "snapshot + closed = official" (the gate's worst was 0.017%).
  - Companies dissolved on or after the snapshot date are left out, because they are still in the snapshot.
- **Codex review 1 (FAIL), all fixed.** It found:
  - partial backfills could pass
  - a 0.1% tolerance too loose
  - types silently filtered before the check
  - null cessation dates counted
  - resume trusting any file
  - identifiers stored without a stated policy
- **Codex re-review (FAIL):**
  - **Fixed:** coverage rows weren't checked as exactly one per quarter, and a null `company_type` dodged `NOT IN`.
  - **Partly accepted, resume contents:** the cross-file uniqueness check catches a duplicated or stale day. No per-file hashes, because the files are local and written atomically.
- **Identifier policy:** company numbers and postcodes stay in `data/` (gitignored), like the snapshot CSV, and are never served. Only protected sums reach the server.
- The first run was stopped after 52 days to apply review 1. Its data was deleted and the run restarted from scratch.
- **Codex re-review 2 (PASS WITH FIXES):**
  - The coverage and missing-type fixes are confirmed sound.
  - **Blocking finding (stale contents could pass), fixed with a content check:** every row's incorporation date must equal its file's day.
  - **No per-file digest:** a digest written by the same process only proves the file hasn't changed since writing. Local tampering is out of scope, and the per-quarter match to official totals is the end-to-end content check.
  - A null company number now gets its own message.

## 2 Nov 2026: backfill finished; check result
- **Download complete:** 2,127 days and 1,996,884 dissolved companies. Every day's retrieved count equals its hits, with no duplicates, blank numbers or misplaced rows.
  - Outside the gate's types: 10,213 LLPs, under 10 overseas companies, under 10 FE college corporations.
- **My cessation-date rule was wrong, now fixed.** I had left out companies dissolved on or after the snapshot date, assuming they were still in the snapshot. A join by company number found 0 of 1,996,963 closed companies in the snapshot, including 14,719 with cessation dates on or after 1 Nov (mostly a strike-off dated 3 Nov). Both sources use the same 8-character numbers over the same ranges, so the zero is real. That rule made every quarter fail (−0.04% to −2.45%).
  - **Fix:** the check now leaves out closed companies by matching company numbers against the snapshot (0 matched), not by date.
- **After the fix:**
  - 22 of 23 quarters are within 0.03% (most within 0.02%), and the three gate quarters reproduce exactly.
  - **2023-Q2 fails:** 178 companies short (−0.084%). The API's own hit counts for that quarter equal the download (120,963), so no download pages are missing. Why the register differs from the official statistic is **unresolved**; one possibility is companies removed from the register or re-dated.
  - **The tolerance is unchanged.** Whether to accept 2023-Q2 as a known residual is James's decision; the builder doesn't pass its own failed gate.
- **James accepted 2023-Q2 as a known gap (2 Nov).** `KNOWN_GAPS` in the check pins the exact shortfall of 178. Any other value for that quarter fails again, and every other quarter keeps the 0.03% bar.
  - **For the build:** answers covering 2023-Q2 closed companies carry a note that the quarter is 0.08% short of the official total.
- **Codex review 4 (PASS WITH FIXES), all applied:**
  - The anti-join is now `NOT EXISTS`. `NOT IN` would drop every closed company if one snapshot number were NULL.
  - Both sides are `upper(trim())`ed, and every number must be 8 letters or digits, else the check stops. All of them passed, and the overlap is still 0.
  - The "known gap" label prints only when the shortfall is exactly 178.
  - The 2023-Q2 cause is marked unresolved.
  - The full output is kept in `active/review/backfill-check-output.txt`.
- **Codex review 5 (PASS WITH FIXES):** uniqueness was checked before normalisation. Company numbers are now normalised as they are read, before every check.

## 2 Nov 2026: closed companies built into the grid (phase B)
- **Live tables unchanged:** `p_uk`, `p_area`, `p_mass`, `areas`, `sic` and `grid` are row-for-row identical to the build before (checked against a backup). Every existing answer and MEMO.md reproduce.
- **New raw table `grid_closed`** has the same columns as `grid` plus `age` (`under_1y` = dissolved within a year of incorporation, else `1y_plus`).
  - **Who's included:** 1,984,989 closed companies (private limited 1,974,390; LLP 10,213; PLC 386). CICs (an API subtype; their own category in the snapshot) and unlimited companies are left out, matching the live grid.
  - **First SIC code:** the API's first `sic_codes` entry, with 99999 or none mapped to "none".
  - **Area:** the same postcode lookup. The pseudo codes (Isle of Man) map to "unmatched", since live data never has them. Unmatched is 0.64% (live 0.08%); closed companies' postcodes are older.
  - **Mass-postcode flag:** uses live counts per postcode, as before, so the cut-off means the same thing.
  - **Snapshot overlap:** checked by company number; the build stops if it isn't 0.
- **New protected tables** `p_uk_closed`, `p_area_closed` and `p_mass_closed`: the same keys plus `age`, the same rounding, and the hash includes the table name. Each is still an area + mass + NI = UK partition, so `pin_check` applies unchanged (it now takes a table suffix and the extra key).
- **Pin repair:**
  - **What happened:** the first build failed the pin check, with 5 cells pinned from one UK closed cell, whose rounding draw left no room for its parts. *(Which cell, and its values, removed before publication: with the values shown here they pinned exact counts below 10. Security panel, Phase D.)*
  - **The pin depends on the rounding draw:** an experiment with other table names gave 0 pinned cells.
  - **The fix:** a UK closed cell that would pin anything is replaced by the sum of its protected parts (area + mass + NI remainder rounded as one cell), so it adds no constraint. 1 cell was repaired, and `meta.closed_pin_repairs` records it.
  - **Not a re-draw:** re-rolling the salt until the check passes would make the published draw depend on the data.
  - **After the repair:** 0 pinned. 7,897 small closed cells are narrowed but not pinned (live: 3,739), the same accepted residual.
- **Live and closed tables don't constrain each other:** they cover disjoint companies and no "all" table is published. An all-registered count is a server-side sum of a live and a closed protected value.
- The server doesn't read the closed tables yet. A test checks that they're multiples of 5, that their areas are a subset of the live area list, and that the server never reads `grid_closed`. **Tests:** 59 pass.
- **Codex grid review (PASS WITH FIXES):**
  - It confirmed 0 pinned cells in both families and the six live tables identical.
  - It confirmed the mapping rules in code; this was not checked against raw records.
  - The findings are documentation and a contract for the server step:
  - **The repaired UK cell uses a different rule:** the sum of its parts, not one rounding. Its error can exceed ±4, so its likely range is understated slightly. The server will **not** widen the range for it, because a data-dependent width would reveal which cell was repaired. This is accepted, since it affects 1 cell in 16k UK closed cells.
    - **Detectability:** a client could notice the UK value equals its parts, but equality also happens by chance, so this reveals no raw count.
  - **Release contract for the closed tools:**
    - `cells` counts every protected cell summed, from the question's shape. For example, live + both closed ages is 3 cells per SIC and quarter.
    - The 1-year survival numerator is under_1y; the denominator is live + both ages.
    - The < 10 rule applies to every released result.
    - No new independently rounded "all" or age total is ever stored.
    - The 2023-Q2 note goes on every answer that includes that quarter's closed data.

## 2 Nov 2026: server tools for closed companies (phase B)
- **`count_incorporations_still_live` gains `include_closed`** (default False, so every earlier answer, the benchmark and MEMO.md are unchanged). True adds the closed protected cells to the live ones, server side, and says how many of them have since been dissolved.
  - `cells` is 3 per SIC and quarter (live + two age buckets), per the release contract, for ranges, the quarter change test and the mass count.
  - Its first must-quote caveat swaps the survivorship warning for the opposite one: closures lag real failures, and companies in liquidation or being struck off still count as open.
- **New tool `one_year_survival`:** the share of companies registered in a period that were not dissolved within a year.
  - **Numerator and denominator:** dissolved within a year = `under_1y`; the rest = live + `1y_plus`. Both parts must be at least 10, or no rate is shown.
  - **Periods:** only quarters whose companies have all had a full year (to 2025-Q3 for this snapshot); default the latest four.
  - **One area:** compared with the rest of Great Britain by a log odds ratio test, with each count's own rounding variance (the new `release.odds_z`; `share_z` now calls it, and MEMO.md reproduces exactly). Same cautious/bold tiers as the ranking. It carries the picked-area caveat.
  - **UK:** the national rate (including formation-agent addresses and NI), the GB rate without them, and the council areas ranked by evidence tier, then by strength, with the Bonferroni bar for the number of areas tested. Both directions are labelled ("lower/higher survival").
  - **Precision:** a rate shows one decimal only when both parts are at least 100; otherwise whole percent.
- **Unmatched postcodes:** answers that include closed companies quote the combined share (0.16%), computed from protected sums only.
- **2023-Q2 note** goes on any answer that uses that quarter's closed data, and only then (tested).
- **Not done:** no likely range on survival rates; the verdict carries the uncertainty. Add one if users ask for it.
- **Caught before review:** adding `include_closed` silently switched `memo_numbers.py` to closed-inclusive counts, because a direct Python call gets the `Field` object (truthy) as its default. Fixed by passing False, with a test that the script still prints MEMO.md's shares, and a note in CLAUDE.md.
- **Tests:** 70 pass (11 new).
- **Codex tools review (FAIL), checked finding by finding:**
  - **Rejected, "share_z now gives the rest of GB the area's cells":** `odds_z` pairs cells with (a1, b1, a2, b2), and `share_z` passes (cells_a, cells_n, cells_a, cells_n), the same as before. Over 10,000 random cases the old and new formulas differ by exactly 0, and MEMO.md's z is still −0.58.
  - **Rejected, "the UK ranking misses one area's cells":** the rest of GB for one area is the other named areas plus the unmatched row, which is `len(names)` areas. That's what the code uses, and it matches `rank_areas_against_great_britain`.
  - **Rejected as a disclosure, "rates and registered counts across calls can constrain a suppressed under_1y count":** every rate is a function of protected values only. The SPEC guarantee is about raw counts, and the pin check already assumes every protected value is known. Knowing a hidden protected sum (say 5) reveals no raw count beyond that accepted model. The "fewer than 10" display stays as defence in depth, not the guarantee.
  - **Fixed, "the caveat overstates the mechanism":** owners can apply to dissolve a company without missing a deadline. The caveat and README now say that dissolved isn't stopped trading, and that unless its owners apply, a company is struck off only after a missed filing deadline. Tested.
- **Codex tools re-review (PASS), fresh context:** it agreed with all three rejections and checked them itself. The two formulas match term for term. The grid has 351 GB rows including unmatched, so the rest of GB for one area is 350 = `len(names)`. `pin_check` reads every protected value in both families and finds 0 pinned raw cells. It agreed the caveat fix is accurate and found nothing new blocking.
  - **Residual, stated plainly:** a hidden *protected* sum (for example, an area's "fewer than 10" early dissolutions) can be inferred from rates and counts in other answers. No raw count can be. The guarantee is about raw counts, so this is accepted, and the "fewer than 10" display remains a second layer.

## 2 Nov 2026: phase C benchmark designed (not yet run)
- **Set-up:** MCP A (pinned, 0 vulnerabilities), installed in `market-pulse-bench/ch-mcp`, outside the repo. A wrapper reads the key from `.env`.
- **Files:** truth in `scripts/truth_c.py`, from exact raw counts; rubric in `active/benchmark-c/RUBRIC.md`; harness in `scripts/benchmark_c.py`, reusing `benchmark.py`'s runner.
- **What the truth shows:**
  - No tested area clears the multiple-testing bar for cleaning growth or survival, once formation-agent postcodes are left out.
  - The national trend flips with the definition: +24% for companies still open, −12% for every company registered.
  - With agent postcodes kept in, Hackney (+151%) and Cardiff (64% survival) clear the bar, both formation-agent effects.
- **Codex design review (FAIL), all fixes applied:**
  - **Questions:** reworded neutrally, with no Market Pulse concepts such as formation agents or the national trend.
  - **The other agent's set-up:** it now gets the ONS postcode lookup, the same $4 budget and the same timeout.
  - **Labelling:** the test is an existing-MCP feasibility test, and its limits are disclosed.
  - **Key safety:** the key is stripped from every agent's environment. It's cut from the raw output before anything is parsed or written, and an empty key stops the run.
  - **Rubric:** the method lines are reported separately from the core lines. Ranking measures are declared (share change or absolute increase), and acceptable cohorts are defined. The truth gains agent-kept-in variants and an absolute-increase list.
- **Found while fixing:**
  - **Search cap:** reading MCP A's code, one search returns at most about 1,000 results and needs a company-name fragment. Disclosed in the rubric.
  - **Advanced search page size:** it passes `items_per_page`, but the advanced search API takes `size`, so it may return only 20 per page. Unverified.
- **Smoke run blocked:** auto mode refused to start the downloaded package with the key. James runs the benchmark, or allows it.
- **Codex design re-review (FAIL), fixes applied:**
  - The key check now also scans stderr, which is never written.
  - The Q2 cohort (incorporated October 2024 to September 2025) is fixed in the question, so one truth scores every answer.
  - R2 needs a stated measure, scored against that measure's list. The truth gains a % growth list (areas with 10+ in the earlier year).
  - R3, S1 and S2 now have explicit qualifier rules.
  - It confirmed from source the search cap at offset 900 and the required name fragment. The page-size question is still unverified.
- **Codex design re-review 2 (PASS WITH FIXES), applied:**
  - R2 now separates "strength of evidence" (z table) from "change in share of GB" (a new list).
  - The scoring contract fixes SIC 812xx and the unmatched rule. Answers using other definitions get "n/a" on R2, R7 and S5.
  - R7 and S5 need a GB figure.
  - It confirmed both earlier FAILs are fixed: neutral questions, equal set-up, and key handling on both streams, redacted before anything is written.
- **The design is ready to run.** Auto mode blocks starting the downloaded package with the key, so James runs it.

## 2 Nov 2026: phase C benchmark run (James ran it; auto mode blocked me)
- **12 runs, no key leaks, no repo access.** Results are in `active/benchmark-c/RESULTS-C.md`, with every figure from `scripts/truth_c.py`.
- **MCP A answered neither question at council level (0 of 6).** Every run said so and explained why:
  - 20 results per page, as the runs reported
  - about 1,000 results per query at most
  - a company-name fragment is required
  - results can't reach Python
- **Market Pulse answered all 6,** about 3–6× faster and 3–15× cheaper (medians), with the same answer every run.
- **Found by checking against exact counts:**
  - **Q2 is wrong:** the survival ranking is a rounding artefact. Its 5 lowest areas really have 80–95% survival, not 67–75%. Protected sums reach the 10-dissolved bar in 21 areas, exactly in 4. The cause is ranking on protected small counts, which selects areas where rounding went up.
  - **Q1 is overstated:** "likely stands out" for Basildon and Slough doesn't hold on the exact counts (z 2.36 and 2.02 against a bar of 3.67).
  - **Both come from the bold-z tier,** which ignores rounding.
- **The rubric scored Market Pulse well,** because it qualified every claim. That's recorded as a rubric gap.
- **Open:** a fix to the survival tool and the ranking tiers, which is James's decision. Codex reviews the scoring next.
- **Codex scoring review (PASS WITH FIXES), all applied:**
  - **Four scores corrected,** all lines where the builder had been too generous to the ch agent: M3 for Q1 r1 and r2, S4 for Q2 r1, and M4 for Q2 r3.
  - **The headline now separates** producing a GB-wide ranking (Market Pulse 6/6, ch 0/6) from that ranking being right (Q2 no).
  - **It checked the rounding artefact itself:** Highland under 10/27 exact against 10/30 protected; Aberdeen under 10/33 against 10/30; Wigan under 10/31 against 10/35. It also noted that rounding the earlier Q1 year down inflates the apparent rise.
- **Phase C fix, approved by James:**
  - **Rounding-blind tier removed:** the "likely (rounding could explain it)" tier is dropped from `rank_areas_against_great_britain` and `one_year_survival`. Verdicts and ordering now use the z that allows for rounding.
  - **`release.rate_range`:** the delta method, with Poisson variance plus rounding variance per cell. Survival rates carry likely ranges, except GB sums over every area, where the cell count makes a range useless and the count is large.
  - **Permanent tests against the raw grid** (tests may read it; the server never does):
    - Every standout must hold on the exact counts.
    - Every survival range must contain the exact rate.
    - No answer may say "rounding could explain".
  - **Kept unchanged:** `compare_area_with_great_britain`'s single-area "possible (borderline)" verdict. It isn't selected from many areas, and MEMO.md uses it. Flagged for Codex.
  - **Rerun, Market Pulse only:** all 6 answers lead with "nothing clearly stands out", which is correct. 83 tests pass.
- **Codex review of the Phase C fix: PASS WITH FIXES** (`active/review/codex-fix-c-review.md`). Both fixes are applied:
  - **Medium:** `share_change` no longer gives "possible … (borderline)" from the z that ignores rounding, so the compare tool says "no clear change" instead.
    - MEMO.md's robustness row is reworded to match.
    - Its numbers are unchanged: share 1.03% to 0.90%, z = −1.64.
  - **Low:** the exact-count ranking test now calls the tool directly with every area (past the limit of 25).
    - It asserts that every tested area is returned and that rows are ordered by tier.
    - Honest limit: only 1 of the 8 cases (retail, shrinking) has a standout, so the exact-count check covers one row; the others pass by having none. That is the conservative direction: the cautious test can miss standouts, but shouldn't invent them.
  - **Low, no change:** small industries get wide survival ranges, and the under-10 rule stays.
  - **Re-review: PASS WITH FIXES, one Low wording fix applied.** MEMO.md now reads "clears the 2-sigma rule only when rounding is ignored (z = −2.17; −1.64 allowing for it)"; it previously said "only if rounding moved no cell". Code findings 1 and 2 are confirmed fixed (`active/review/codex-fix-c-rereview.md`).

## 2 Nov 2026: phase D (Codex review fixes, handover and security gates)
- **Fixes from `active/review/codex-review.md`:**
  - **Serving database:** `scripts/export_serving.py` writes `data/serve.duckdb` with only the 6 protected tables, `areas`, `sic` and `meta`. The server opens only that file. `build_grid.py` runs the export at the end, and a test checks the table list and that no `companies` column exists.
  - **Wording:** "real" is now "clear … in this snapshot".
  - **`answer` field:** every CountResult carries the summary plus both must-quote caveats in one field.
  - **SIC guidance:** find_sic and the codes field now say matches are sorted by code, not relevance, and give the cleaning and digital examples.
  - **README:** a data sources and licences section with hashes, links and attributions. The Companies House reuse statement is quoted from its forum (service owner, 4 Nov 2021); the ONS attributions were checked on its licences page. Also MIT `LICENSE`, the SPEC status, and the review key renamed to `reviewer-map.txt`.
- **Codex review of phase D: PASS WITH FIXES** (`active/review/codex-phase-d-review.md`), all applied:
  - **The privacy wording now describes the exact check:** per code and quarter; UK, area and mass tables; open and closed.
  - **The e2e quote check passed when nothing was quoted.** It now reports word-for-word quoting separately.
  - **A failed build leaves the last serve.duckdb in place,** and the README now says so.
- **The end-to-end rerun showed the harness was stale since phase B.** Clients now choose `include_closed`, and its wording didn't match the harness's live-only and summary patterns. With the patterns fixed, a run with no tool calls is flagged, and the SPEC gate is 5/5.
  - **Word-for-word quoting of the summary is 6/15**, against 15/15 in v1. Changing the instruction from "quote `answer`" back to "quote `summary`" didn't change it, so the longer phase B sentence is the likely cause [U]. No answer invented a quote, and every answer kept the date and the survivorship caveat.
- **Handover gate:**
  - **Rule 2 fixed:** error logs had no timestamp or intent. Now each line gives the timestamp, the tool and the arguments it was answering. basicConfig needs `force=True`, because the MCP library sets up logging first.
  - **Rules 1, 4 and 5 pass.** Rule 3 (alerts) is not applicable: there is no scheduled job, and errors go straight back to the person asking.
- **Security checklist:**
  - **Stage 0:** gitleaks, semgrep and osv-scanner aren't installed. In their place: an exact-value search of all history for both secrets (none found) and an OSV.dev batch query of all 34 packages (no known vulnerabilities).
  - **Stage 1:** most items are web-app only (auth, sessions, CORS, CSP, cookies). Agent ignore rules for `.env` and raw data were added.
  - **Stage 2 panel:** three fresh Claude reviewers plus Codex.
    - **Medium, fixed:** parallel tool calls shared one DuckDB connection. On that old connection, 53 of 120 parallel calls failed or returned another query's numbers. Each thread now gets its own cursor, and a regression test runs 12 calls in parallel.
    - **Medium, fixed:** tracked docs published exact counts below 10. `truth.md` and the RESULTS-C table had benchmark truth, and this file had the pinned-cell details. truth.md is no longer tracked, survival is shown in bands, and the cell details are removed. **They are still in git history**, so publish with fresh history.
    - **Low, fixed:** blank search text matched everything.
    - **Low, fixed:** README wording on subtracting, an "official statistics" disclaimer, and multi-build comparison stated as not covered.
    - **Open for publication:** tracked transcripts hold local paths, session IDs and about 85 real postcodes (in the competitor agent's transcripts).
    - **Open for James, closed 5 Nov 2026:** whether to identify Northern Ireland by the BT postcode prefix, to avoid using the Land and Property Services data at all. He chose the prefix (see the 5 Nov section on decisions before publishing).
- **Codex re-review of the phase D gates: PASS WITH FIXES** (`active/review/codex-phase-d-rereview.md`):
  - **Fixed:** the caveat check accepted "dissolved since" without the lag explanation. It now needs struck off, lag, filing deadline or stopped trading. Rescored: still 5/5.
  - **Fixed:** search tools' free text could reach an error log. They now log only the tool name.
  - **Reported, not changed:** the SPEC gate doesn't require word-for-word quoting (6/15). Raising it would mean shortening the include_closed summary sentence, which is James's call.
  - **Accepted:** the parallel test checks for swapped answers, not cursor configuration. Cursors inherit the read-only connection, as Codex confirmed.

## Testing phase (2 Nov 2026), before security stage 3 and publishing, on James's direction
- **Plan approved by James** ("yes go ahead, 2 runs, include the companies house one"):
  - 8 case studies, each run 2 times on 3 agents: Market Pulse, plain web search, and MCP A (run by James, with his key).
  - 15 break-it questions, a free consistency sweep, a hands-on guide for James (`active/testing/TESTING-GUIDE.md`), then a results write-up and a Codex review.
  - Design and rubric fixed before any run: `active/testing/CASES.md`. Codex reviewed the design (READY WITH FIXES, all applied).
- **Sweep** (`scripts/sweep.py`): every SIC code through every tool, every area through the area tools, plus 15 refusal cases. Run 1 found a real bug: an unknown 5-digit code answered "fewer than 10". It is now BAD_SIC.
- **Harness fix:** the small-count check matched across a line break ("nearest 5:" then a table header). It now stays on one line, with self-tests.
- **Break-it judged by Codex: HOLDS WITH FIXES** (`active/review/codex-breakit-judge.md`). 15 of 30 PASS, 15 PARTIAL, 0 FAIL. Small counts stayed protected in all 30.
  - **Server fixes applied:**
    - `['all']` gives an all-industries total (B13: agents added up divisions by hand and couldn't show they covered every code).
    - 99999 now counts under 'none' (B5: it answered BAD_SIC, though dormant companies use it).
    - The ranking tool says it doesn't show which area grew fastest (B11).
    - The comparison tool says testing two areas against GB doesn't rank them against each other, and a new caveat says a registration is not a business opening (B15).
  - **Model errors, not changed:**
    - B2 r2 miscounted rows and gave the wrong end date.
    - B4 gave Tesco facts from memory; the server has no company lookup.
  - **B6 forecast and B12 quote: PASS.** Both were labelled as the model's own estimate or paraphrase.
- **The case runs predate these fixes.** The Market Pulse case answers came from the server before the break-it fixes. The fixes change no number those cases would get. The new docstring lines and caveat may change how agents word their answers.
- **Break-it reruns after the fixes** (old answers in `active/testing/breakit/v1/`, the first B11 rerun in `v2/`):
  - **B13 fixed:** both rounds use `['all']` in one call (about 191,665, with a range).
  - **B5 fixed:** one round counts under 'none' and says so; the other asks which code was meant.
  - **B15 improved:** both rounds now say registrations aren't openings, and the data can't show one city grew faster. One round still heads a list "Opened in the last year".
  - **B11 partly fixed.** The docstring line alone changed nothing, so a ranking caveat was added: "This ranks evidence, not growth…". Round 1 then checked Hackney with the compare tool and answered from that test. Round 2 still answers "No" from the ranking alone. Accepted: the question demands yes or no, and the caveats were kept.
- **Case scoring by a fresh Codex** (`active/review/codex-cases-score.md`; 48 runs, quotes for every point):
  - **Core points:** Market Pulse 82 (5.1 per run), MCP A 74 (4.6), web 36 (2.3).
  - **Code-set zeros:** in C6, C7 and C8 the agent chose codes outside the rubric's sets, which scores 0. Checked against exact counts for the codes it used (`scripts/check_cases.py`), its numbers were within 4%.
  - **Two real failures, confirmed against exact counts:**
    - **C2:** the area breakdown showed 7 vape areas as 10–15; exactly, all were under 10.
    - **C4:** the survival ranking missed North Yorkshire and Stratford-on-Avon. Its "closest candidates" led with areas shown as 10 dissolved that were exactly under 10.
  - **The Phase C fix tested only verdicts and ranges, not which rows a list picks.** Logged as a repeat in `~/.claude/RSI.md`.
- **List fix, approved by James** ("yes do the fix first"):
  - **First version FAILED review** (`active/review/codex-list-fix-review.md`):
    - **The gate:** it picked areas whose likely range started at 10.
    - **The variance cap:** it capped the rounding variance at min(cells, protected count), so the lists didn't drop almost everything.
    - **Why it failed:** the cap isn't a bound. Rounding can hide occupied cells (nine 1s can show as 5), and a read-only check found 1,852 counterexamples. My argument had used the protected count where it needed the true one. Logged in `~/.claude/RSI.md`.
  - **Revised version:**
    - **The variance cap is removed.**
    - **`release.surely` is now certain:** the true sum is at least n − 4 × min(cells, n // 5). A cell shown as p ≥ 5 holds at least p − 4, and at most n // 5 cells can show 5 or more.
    - **Where it applies:** every area entering the area breakdown's numbered rows (the rest read "under N" or "fewer than 10", listed by name), the growth ranking and the survival ranking, and the rest-of-GB counts in both rankings.
    - **When no area clearly differs:** survival rows are listed by name, not ranked.
    - **Plain answer when nothing can be tested.**
  - **New permanent tests:**
    - An exhaustive check of the bound over every rounding of up to 4 cells.
    - Exact-count checks on every row each list picks, across 5–7 industries. 14 of 22 fail on the old code.
  - **Cost, accepted as honest. A certain floor misses smaller real changes:**
    - Construction survival at council level tests 0 areas, so North Yorkshire and Stratford-on-Avon can't be found from rounded data.
    - The cleaning growth ranking tests 36 areas, not 209. It drops Medway (exactly 32 → 72, the exact leader) and Hackney.
    - Retail (47) survival tests 12 areas, food and drink (56) tests 3, and all industries tests 173.
  - **Checks:** 117 tests pass, the sweep finds 0 problems, and C2 shows no vape area with a number.
  - **Re-review: PASS WITH FIXES** (`active/review/codex-list-fix-rereview.md`). Per Codex, a cell-by-cell floor replaces `surely`.
  - **Third version** (`active/review/list-fix-v3.diff`):
    - **The floor:** each protected cell holds at least max(p − 4, 0). It is summed cell by cell, a tighter floor that is still certain.
    - **Lists show standouts only.** Areas that could be chance are no longer listed in score order, because an order on chance reads as a ranking.
    - **Review:** PASS WITH FIXES (`active/review/codex-list-fix-v3.md`). The ranking test had become vacuous, so new tests recompute eligibility and standouts independently from protected data, plus a survival case checked on exact counts.
  - **The new survival test failed, which exposed a real bug** (`scripts/check_standouts.py`, every standout across 88 divisions and 4 periods, checked on exact counts):
    - **What it showed:** Food (56) 2021 named Tower Hamlets "lower survival … even allowing for rounding", shown with 50 dissolved within a year. Exactly 22 were, and the exact z is 0.19 against a bar of 2.24. Construction 2023 named Hounslow (exact z 1.70). In all, 2 of 4 survival standouts didn't hold; all 8 growth standouts did.
    - **Root cause:** the 10-for-certain gate is computed from rounded cells, so the areas that pass it are mostly ones whose cells rounded up. The multiple-testing bar counted only those areas (2 for food 2021), so the selection on noise went uncorrected.
  - **Fourth version:** in both rankings, the bar counts every council area in Great Britain (350), because which areas pass the gate depends on rounding. Bonferroni over the whole family holds whatever subset is looked at.
    - **Result on exact counts:** survival names 0 areas in any of the 88 divisions and 4 periods; growth names 6, and all 6 hold.
    - **Cost, accepted:** construction 2023-Q4 to 2024-Q3 loses North Yorkshire, a true standout (exact z 8.0 against a bar of 3.8). The rounding allowance (6.25 per possible cell, about 120 cells per part) is loose, and Codex's v3 review says a tighter one needs a proof from released values only. Open item, not attempted.
    - **The one-area tools are unchanged:** a single area the user names isn't selected on noise, so the single-test bar of 2.0 stays. Its stated risk is the usual 5% per question.
  - **Checks:** 131 tests pass, the sweep finds 0 problems, and C2 still shows 0 numbered vape areas, matching 0 exactly.
  - **v4 review: PASS WITH FIXES** (`active/review/codex-list-fix-v4.md`):
    - **High: the one-area wording overclaimed.** Asked about directly, Tower Hamlets food 2021 is called lower (cautious z 2.59 against a bar of 2.0), while its exact z is 0.19. A threshold on rounded counts isn't a guarantee about the exact counts. **Fixed:** no verdict says "even allowing for rounding" any more. They now say "on a test that allows for rounding (not certain: rounding can still mislead it)", from one constant, `NOT_CERTAIN`. The README says a verdict is a statistical call.
    - **Medium: the growth test's own bar** used the tested count, not every area. **Fixed:** it now uses every area, and asserts the summary says so.
    - **Medium: the survival exact-count check runs on no rows in this snapshot.** **Fixed:** a synthetic test (protected sums read as exact) where one area truly loses 40% against 10% elsewhere must be the only row, and must clear the every-area bar. Tower Hamlets stays as the real negative case.
    - **Codex's statistical judgment:** counting all 350 areas is the right family. It does not prove a 5% family error rate, because the cautious z's distribution after a rounding-based gate hasn't been calibrated. On this snapshot, among near-null comparisons (exact |z| ≤ 0.5), the cautious z went above 2 once (Tower Hamlets) and never above 3 or the 3.80 bar. The lists stay exploratory. Restoring North Yorkshire would need a worst-case test over every exact table compatible with the released cells, with a proof. Open item, not attempted.
  - **Checks after the fixes:** 132 tests pass, the sweep finds 0 problems, and the scan gives survival 0 named, growth 6 of 6 holding.
  - **v5 review: PASS WITH FIXES** (`active/review/codex-list-fix-v5.md`). The three v4 findings are resolved, and the synthetic test fails when standouts are suppressed. Three more verdicts still read as certain:
    - "clear rise/fall in share in this snapshot" (one-area growth) and "clear increase/decrease in this snapshot" (quarter to quarter). **Fixed:** both now end "(a test that allows for rounding, not certain)", from one constant, `release.TEST_NOTE`. They still start "clear", so the code that reads them is unchanged.
    - The survival summary's "clearly differs". **Fixed:** it now says "No area passes this test" and "the areas that pass this test".
    - **Checks:** 132 tests pass, the sweep finds 0 problems, and the scan is unchanged.
- **Rival arms and Market Pulse rerun:**
  - **Runs:** MCP B (James ran it) and MCP C each did 16 runs, with no errors and no audit flags. The Market Pulse case arm was rerun on the final server. Its old runs are kept in `active/testing/cases/v1-before-list-fix/`.
  - **Medians** (from `cases.py metrics`, which now prints a per-agent table):

    | Agent | Time | Cost | Tool calls |
    |---|---|---|---|
    | Market Pulse | 18s | $0.04 | 5 |
    | web | 52s | $0.09 | 5 |
    | MCP C | 148s | $0.14 | 8.5 |
    | MCP B | 151s | $0.87 | 31 |
    | MCP A | 178s | $0.61 | 35 |

- **Second scoring, by a fresh Codex** (`active/review/codex-cases-score-2.md`, same rubric and truth):
  - **Core points (mean per run):** Market Pulse 83 (5.19), MCP B 70 (4.38), MCP C 59 (3.69). The first scorer's results: Market Pulse before the fix 82 (5.12), MCP A 74 (4.62), web 36 (2.25).
  - **Agreement:** on the 8 runs both scorers marked, 39 of 48 line scores agree. Of the 9 disagreements, the second scorer says the first scorer's mark is the better one on 3.
  - **Where the rivals break down:** MCP B's counts come out too high in C1–C3, and its C2 council ranking is about double the truth. MCP C can't build cohorts (it has no date or status filter) and called growth from a base under 10.
- **Limit found:** the case harness saved tool calls but not tool results, and the agents' transcripts weren't kept. Numbers can only be checked against the truth, not traced to what each tool returned. To fix, save the results in `benchmark.run` before any rerun. Not done.
- **Fixed from the scoring, C2:** areas without 10 for certain showed "under N". N was the top of a likely range, so it wasn't certain, and a higher N only meant rounding went up. Run 2 called Nottingham the "likeliest leader" on that basis. Every area row without 10 for certain now reads "too few to number for certain", with no figure. The alphabetical order is stated as meaning nothing. The sample: all 351 areas carry the one label, matching the exact counts (none has 10). Tests (132) pass and the sweep finds 0 problems.
- **Area-label review: FAIL** (`active/review/codex-area-label.md`):
  - **High: an area the breakdown hides still gets a number when asked about alone** (28 areas for cleaning in 2021-Q1, every registered), so many single-area calls could rank them. Codex offered two fixes: hide those answers too, or narrow the contract. Hiding them would drop most small single-area numbers, and asking about one area isn't selecting on noise. **Contract narrowed instead:** the breakdown summary and the server instructions both say single-area counts can't rank areas the breakdown leaves unnumbered.
  - **Medium: the total minus the numbered rows gives the hidden rows' sum.** That sum is of rounded cells, never an exact count, and the release-unit decision (1 Nov, fourth review) allows sums and differences of rounded cells. **Kept.** The test comment wrongly said rounding the total stops subtraction. It now says what's true.
  - **Low: the test checked only the label.** It now checks every field of the hidden rows (uniform apart from the area), alphabetical order, numbered rows first, and both summary sentences, with and without closed companies.
  - **Checks:** 133 tests pass and the sweep finds 0 problems.
  - **Re-review: PASS WITH FIXES** (`active/review/codex-area-label-v2.md`):
    - **Medium: the narrowed contract claimed too much.** Rounded single-area counts can be put in order; what they can't show is which area truly has more. **Fixed:** the summary and the instructions now say exactly that.
    - **Low: the residual is allowed, but untested.** With one hidden row, it can show that row's rounded value, even below 10. That is a presentation inconsistency, not a breach, under the release-unit decision. **Fixed:** a test in a mixed breakdown (all industries, 2021-Q1, 4 hidden rows, residual 100) and in an all-hidden one (vape, 351 hidden, residual 65) checks the residual is exactly the hidden rows' protected sum. The README names the new label and already says subtracting gives a protected value, never the true count.
    - **Checks:** 135 tests pass and the sweep finds 0 problems.
  - **Third review: PASS WITH FIXES** (`active/review/codex-area-label-v3.md`). The v2 findings are resolved, and the residual test fails when a hidden row moves by 5. One low finding, wording only: a rounded sum can equal the true count by chance, so "never the true count" was too strong. **Fixed:** the test comment and README line 35 now say the residual "doesn't establish the true count". Also dropped a dead term in the test; the unmatched area is itself a row. 135 tests pass.
- **Not taken:** the scorer's C4 fix ("rework the test on exact counts before rounding") would read unprotected data at query time, which the design forbids. Losing North Yorkshire stays an accepted cost, as above.
- **Two more existing MCPs, on James's go-ahead ("add both MCPs, skip nomis"):**
  - **MCP B** (pinned to one commit):
    - **What it offers:** the live API, including advanced search by incorporation date, SIC and location, which returns a hit count.
    - **How it was installed:** built from the source that was read, with `npm ci --ignore-scripts`.
    - **Audit:** its only outside addresses are the Companies House APIs.
    - **Vulnerable packages:** npm audit flags 10, all in the SDK's HTTP-server stack. That stack isn't used over stdio.
    - **Who runs it:** James, with his key.
  - **MCP C** (pinned to one commit, no licence, so we only run it and copy nothing):
    - **What it offers:** the same bulk file in SQLite, searchable by name or postcode, with no date filter.
    - **Audit:** all of its code was read. It makes no network calls and is read-only.
    - **Data:** its database is built from our 1 Nov 2026 snapshot, so nothing new was downloaded.
  - **Set-up:** both get the same set-up as the MCP A arm, Python plus the ONS lookup. The audit flags any read of the wrapper, `.env` or the rival's database file.
- **Testing write-up** (`active/testing/TESTING-RESULTS.md`, numbers from `scripts/testing_results.py`): two fresh Codex reviews, both PASS WITH FIXES, with all fixes applied.
- **James's decisions on it, 2 Nov 2026** ("quote marks only, and try the stronger B11 server wording"):
  - **Quote check:** only a summary sentence inside quotation marks counts as a claimed quote. A rewording in the summary's own form no longer fails the check. A test covers both quotation-mark styles and a rewording.
  - **B11:** every ranking summary now opens with `RANK_LIMIT`: it can't say which area grew fastest, or answer yes or no to whether a named area did. A test checks it.
  - **Review** (`active/review/codex-rank-limit.md`, PASS WITH FIXES): `RANK_LIMIT` claimed listed areas changed "beyond what rounding and chance explain"; it now says they stand out on a test that allows for both, though not with certainty. A test now covers the no-area path, and two write-up lines were corrected. B11 was not rerun on the softened wording.
  - **Re-review** (`active/review/codex-rank-limit-v2.md`, PASS WITH FIXES): all four findings resolved; one low finding, the `scripts/e2e.py` description still said every summary sentence is checked, now says only those inside quotation marks.
- **James, 2 Nov 2026** ("accept B11 as a model limit, and rerun for 5/5"): B11 is accepted as a limit of the model and noted in the README under "Where is it growing fastest?". The end-to-end check is rerun, 3 rounds, with a 5/5 bar.
  - **Rerun result:** 4/5 again. Q3 ("ignore the caveats") failed 2 of 3 rounds: both answers kept the area warning but dropped the must-quote closure-lag warning, which is where the snapshot date sits. Same tool calls as the earlier 5/5 runs, so the model is choosing what to drop. README "AI test" line updated to this run. Rerunning until a 5/5 comes up would be picking the lucky run, so it waits on a server change or James accepting 4/5.
  - **Q3 server change** (James: "do the server change, then rerun once"): with closed companies included, the summary's first sentence ends "including those dissolved by <snapshot date>", and the must-quote closure warning went from 70 to 55 words, keeping "Dissolved is not the same as stopped trading" and the filing delay; the liquidation sentence moved to a caveat that isn't must-quote. Reviews `active/review/codex-q3-date.md` to `-v6.md`: five PASS WITH FIXES (trading distinction, date wording in instructions and descriptions, test meaning, and four rounds of "every company"/"how many started" wording implying a complete count), then PASS.
  - **One rerun:** 5/5, all 15 rounds. It ran before the v4–v6 review fixes, which changed only the include_closed parameter description, the count docstring and the README; served summaries and caveats are as run, but the changed descriptions are visible to the model and weren't rerun.
  - **Write-up reviews** (`active/review/codex-q3-writeup.md` to `-v3.md`): two PASS WITH FIXES (rerun chronology, "final server" scope, README cause and quote-rate claims), then PASS.
- **Reruns on the current server** (James, 2 Nov: "rerun break-it and the case studies on this server"): the case harness now saves tool results (`scripts/benchmark.py`). Market Pulse case runs: 83/92, 5.19 a run, third scorer (`codex-cases-score-3.md`); earlier runs kept in `active/testing/cases/v2-before-q3-date/`. Break-it: 27 PASS, 3 PARTIAL (B5 both rounds, B11 round 1), HOLDS WITH FIXES (`codex-breakit-judge-2.md`).
  - **New finding (case C7):** "fewer than 10" was shown for a true 13. `scripts/check_fewer_than_10.py`: of 65,126 code × area pairs with at least one company in the latest year and shown as fewer than 10, 679 (1.04%) really have 10 or more. Waiting on James.
  - **Rejected:** the scorer's C4 fix (test areas on raw counts); the design forbids reading exact counts at query time.
  - **Small-count check:** one case answer flagged; the match is the "1" of a caveat label. `testing_results.py` now prints the matched text.
  - **Write-up reviews** (`codex-reruns.md` PASS WITH FIXES: "answers" denominator, unmeasured longer periods, label quote, scorer wording; then `codex-reruns-v2.md` PASS).
- **James, 2 Nov 2026** ("reword fewer than 10 and make both fixes"):
  - **Small-count label:** "fewer than 10" is now "under 10 (rounded)" (`release.SMALL`), and any answer using it adds `SMALL_NOTE`: the rounded count is below 10 and the true count may be somewhat higher. Case C7 (Gwynedd 55209, a true 13 shown as fewer than 10) and `scripts/check_fewer_than_10.py` (679 of 65,126 active pairs) are why. README and SPEC updated.
  - **Break-it B5:** every BAD_SIC rejection now ends with `NO_SWAP` (ask the user or use find_sic; never answer for another code), the format rejection no longer mentions 'none', and the server instructions say the same. The 99999-to-'none' mapping is unchanged.
  - **Break-it B14:** the survival no-area sentences say "better or worse" and "best or worst".
  - **Reviews:** `codex-small-label.md` PASS WITH FIXES (harness patterns untested, SPEC threshold wording), then `codex-small-label-v2.md` PASS. 145 tests pass; the sweep finds 0 problems.
  - **Reruns after the fixes:** break-it B5 and B14 (2 rounds each): B5 declines to swap in 'none' and asks, without calling the count tool; B14 uses the new sentence. End-to-end: first scored 4/5, but Q1 round 3's small-count failure was "rounded to the nearest 5 and include companies", the rounding step. `scripts/e2e.py` now exempts only the phrase "rounded to the nearest 5" (review `codex-final-reruns.md`: skipping any digit after "nearest" could miss "the nearest 5 companies"), with tests; the saved answers rescored 5/5 with no new rounds, and break-it rescored unchanged.
  - **Write-up and check reviews:** `codex-final-reruns.md` PASS WITH FIXES (exemption too broad; an old limit read as current; it also confirmed Q1 round 3 a false alarm and judged the four new B5/B14 answers PASS), then `codex-final-reruns-v2.md` PASS.
- **James, 2 Nov 2026** ("do the formation-agent warning fix now"), from hands-on trial 2: London's share of GB for SIC 62012/62090/63110/72190 fell with formation-agent addresses left out but rose with them in, and the model led with "growing more slowly".
  - **Evidence:** `scripts/check_agent_share.py`, exact counts, latest year against the one before, 5-digit codes with 500+ GB companies and areas with 30+. An area's share of GB moves the other way (by 5%+ both ways) with agents put back in for 1-3% of tests when agents are under 20% of GB's companies, 6-7% at 20% or more (London boroughs 14-15%).
  - **Change:** `AGENT_SHARE = 0.2`, a precautionary trigger from that sample, not a proven boundary. When protected sums put agents at 20%+ (and at least 10), the summary says "About N% of Great Britain's companies with these codes registered in ... are at formation-agent addresses, which area figures leave out, so comparing areas, or an area with Great Britain, may mislead." It sits after the first sentence in count area answers, after the verdict in compare, and after the opening limit in rank. UK totals don't carry it (they include agents).
  - **Not done:** survival answers. Their summaries already say agents are left out, but whether that flips survival verdicts hasn't been tested. Open.
  - **Reviews:** `codex-agent-warning.md` PASS WITH FIXES ("mostly in London" was false for 17 codes where it fires: removed; 20% called precautionary), then `codex-agent-warning-v2.md` PASS (one low note on the script's opening line, fixed). 147 tests pass; the sweep finds 0 problems (it now takes 169 s, against 73 s, from two extra GB-wide sums per area answer).
- **User-perspective reviews, 3 Nov 2026** (James: find out how constraining the MCP is for real users). Codex and a fresh Claude reviewer each saw only the README, the tool list and live answers (`active/review/ux/`). Codex: 10 of 36 questions fully answered; Claude: 8 of 49, with design choices the main block in 26 of 41 misses and privacy rules in 2. Merged list: `active/review/ux/synthesis.md`. James approved batch A (answering-side changes, protections unchanged) and wants the rest too: round-once totals, live company counts, a full closures download.
- **Batch A1, regions and nations, 3 Nov 2026.** `find_area` lists the 9 English regions, Wales and Scotland first ("London" was returning only the City of London). Count (including an area breakdown inside a region), compare and survival accept them; a region is the sum of its council areas' protected cells, so nothing new is released, and its range counts every member area's cells. Lookup: ONS LAD25 to RGN25 (April 2025, V2), downloaded 3 Nov with James's go-ahead; the export checks every GB council area is covered once. `scripts/check_regions.py` against exact counts: 1,650 region totals, 5,377 region quarter rows and 412 region survival ranges, none outside; 1 of 7,633 one-council-area rows (the existing method, unchanged) outside its likely range, which a likely range allows. Reviews: `codex-regions.md` PASS WITH FIXES (the region trend used one area's cells; GB quarter rows used one cell; the check missed paths), then `codex-regions-v2.md` PASS. 149 tests pass; the sweep finds 0 problems.
- **Batch A2, everyday words and bundles, 3 Nov 2026** (James: "everyday words don't find codes... that's basically the whole premise"; wants ready-made bundles clearly labelled approximate). `src/bundles.py`: 24 bundles (id, label, codes, a short limit, a full note, trigger words) and about 60 everyday words mapped to one activity's code. `find_sic` matches whole words after normalising case, accents, hyphens and plurals ("AI" found dairy farming and "pet" petroleum by substring before), lists one activity's code first, then bundles, then description matches; nothing found gives NO_MATCH with the bundle ids. A bundle id works as a code; the summary's first sentence reads "the '<label>' bundle (approximate: <limit>; SIC <groups>)", and the full note is a caveat. Rule from review: a trigger must not promise more than its codes cover, so "nightclub", "social care", "payments", "crypto", "food business", "supply chain" and "online business" find nothing rather than a misleading stand-in. Reviews: `codex-bundles.md`, `-v2`, `-v3` PASS WITH FIXES (overpromising triggers, limits only in a droppable caveat, plural and accent misses, salon phrases, "online business"), `-v4` PASS. 150 tests pass; the sweep finds 0 problems.
- **Batch A3, chosen periods and a head-to-head test, 3 Nov 2026** (James: fixed comparison periods, a direct area-against-area comparison, and compare's headline setting a young group against an older one). `window()` gives the later period (default the latest four quarters) and an earlier one: the same quarters a year before (a period longer than four quarters goes back whole years, so the two never overlap) or the same-length period just before; OUT_OF_RANGE names the earliest start that works. Compare and rank take from_quarter and against; compare now counts companies dissolved since by default (`include_closed`, cells x3). New `compare_two_areas`: "X likely had more in <period>" and "X's share of the two together went from a% to b%, so X likely grew faster in percentage terms", each with the rounding note next to the claim; overlapping areas are refused. Nothing finer is released: every figure is a sum of existing protected cells. `scripts/check_two_areas.py` against exact counts: 9,640 pairs (every pair of regions and nations by division, plus 400 random council pairs by 12 large divisions); "more" given 2,503 times and "faster" 4 times, 0 wrong. Faster verdicts are rare because summed rounding widens the test; batch B (round totals once) should help. Reviews: `codex-periods.md` PASS WITH FIXES (year-before shift undescribed; verdicts quotable without the doubt; harness gaps; one finding on the agent warning was a misreading, confirmed by v2), then `codex-periods-v2.md` PASS WITH FIXES ("both years" in rank, fixed). 151 tests pass; the sweep (now with two-area and chosen-period calls) finds 0 problems. The paid end-to-end rerun waits for the end of batch A.
- **Batch A4, a sector breakdown for a place, 3 Nov 2026** (user review: "what's growing in Leeds?"). New `breakdown_by_industry(area, to_quarter, from_quarter, against, include_closed=True)`: for the UK, a region or nation, or a council area, one row per 2-digit SIC division plus 'no activity stated', in SIC order, with earlier and later counts, a verdict ("likely rose", "likely fell", "no clear change", "too few to test"), and for areas the same verdict across Great Britain; the summary adds a test on the place's total. The bar is raised (Bonferroni) for all 89 rows, not just those passing the at-least-10-for-certain gate (RSI: size the family by every candidate). `release.change()` gains `tests`; `protected_sum` allows grouping by code internally, and only division sums are published, each a sum of existing protected cells. Plain division names in `src/bundles.py` (DIVISIONS). `scripts/check_breakdown.py` against exact counts, two settings (default closed; 2026-Q1 to Q3 against the quarters just before, open only), 724 place-settings: 109 division, 4,693 GB and 21 total verdicts, 0 wrong. It checks stated directions only, not missed changes or the chance firing rate. Few verdicts for single council areas: totals add up hundreds of separately rounded cells (Leeds, all industries: about 7,840 against 8,310 is "no clear change"); batch B should help. Harness: e2e adds Q6 (what's growing in Leeds) and Q7 (Bristol or Manchester for cafés) with a check that the client chose the tool built for it, and its quote check now recognises every tool's summary (rank and survival were never covered: an invented quote of either passed). Reviews: `codex-breakdown.md` PASS WITH FIXES (rows' counts could be read as a ranking; no e2e question; checker limits; SIC 01 name), `-v2` and `-v3` PASS WITH FIXES (quote pattern missed closed breakdowns, then rank and survival), `-v4` PASS. 152 tests pass; the sweep finds 0 problems.
- **Batch A5, refusals that point somewhere, short replies, two slips, 3 Nov 2026** (James: "give it the next best thing"; "provide a short answer first, and then... do you want me to explain further?"). A quarter before 2021 is refused with a pointer to ONS 'Business demography, UK' (VAT/PAYE businesses, not company registrations). Too-few outcomes in compare, two-area and survival name only the widenings still open (wider codes, a longer period, the region each council area is in) and say a wider question is a different question, or that this data can't answer at this level. The sole-traders caveat and the instructions name the government's 'Business population estimates for the UK and regions' (estimates) and ONS 'UK business: activity, size and location' (VAT/PAYE-registered, a stand-in for trading); source names checked on GOV.UK/ONS search results. Short replies: the first attempt ("quote the opening sentence and verdict") was rejected in review because clients could drop safety sentences (agent warning, low-count caution, rank's limit, a second verdict); the instructions keep "quote `summary` word for word plus both must-quote caveats", and add: start with them, keep extra explanation brief, include rows only if asked, otherwise offer more detail. Baseline before this: median 269 words per answer (`scripts/e2e.py words active/e2e/before-batch-a`). Slips: survival ranges widen precision until the ends differ ("likely 95%–95%"); the 'Under 10' note now appears only when the summary or a row shows that label (accepted in review: the agents caveat labels its own figure). Reviews: `codex-a5.md`, `-v2`, `-v3` PASS WITH FIXES (short-first could drop safety text; suggestions offered widenings already used, a region for the UK, an unnamed region for two areas; tied range ends), `-v4` PASS. 153 tests pass; the sweep finds 0 problems.
- **End-to-end after batch A, 3 Nov 2026** (`scripts/e2e.py 3`, Sonnet 5.5 client, 21 answers, $0.67): 7/7 on the automatic checks (date, survivorship caveat, no exact small count, no invented quote, right tool for Q6 and Q7). Two problems the checks don't catch. (1) Length barely moved: median 260 words against 269 before; Q4 and Q6 run over 400. Clients now open with the summary word for word (it is no longer in quotation marks, so the 'quoted verbatim' count reads 0/21), then add their own sections. (2) Q6, "what's growing in Leeds": the summary says no division shows a clear change, but the client then listed the "biggest industries" and the divisions that "moved the most" from the rounded row counts, despite the tool description and summary saying not to. One Q7 answer led with "Manchester has more new cafés", dropping the "likely". Open: whether to drop counts from rows that have no verdict, or keep them and accept the risk; James to decide.
- **Breakdown rows: counts hidden where no change is clear, 3 Nov 2026** (James chose this over showing ranges or keeping counts). Review `codex-breakdown-hide.md` PASS WITH FIXES (wording narrowed). End-to-end rerun ($0.65): 7/7; median 256 words (269 before batch A). Q6: none of the three answers ranked divisions any more. All three said no division shows a clear change, and two quoted the summary word for word. One round overstated the absence ("Leeds is not shrinking or growing in any particular sector... ordinary noise"): no clear change is not shown to be no change. Open, minor.
- **Batch B, totals rounded once, 3 Nov 2026** (James: "go batch B"). New protected cells for every total a tool asks for: council area, region or nation, GB and UK, each by 5-digit code, 3-digit group, 2-digit division and all industries, per quarter (`p_agg`), by age for closed companies (`p_agg_closed`), plus companies registered before 2021 and still live (`p_pre2021`, `p_pre2021_mass`). Council x code and UK x code are copies of the existing tables. `scripts/build_levels.py`.
  - **First design rejected:** rounding every new total on its own gave 2,951 pinned and about 1.7 million narrowed small counts, because small totals sat on small parts.
  - **Threshold rule:** a new total is rounded on its own only when its parts' shown values add up to 50 or more (`INDEPENDENT`); otherwise it is published as that sum, which adds nothing. Whether a total is rounded on its own depends only on published values. The server treats a cell shown at 50 or more as one rounded cell, and anything smaller as all the parts under it.
  - **Pin check rewritten** (`scripts/pin_levels.py`): the Python worklist ran 2.5 hours and 9 GB without finishing (quadratic re-summing on UK totals); it is now set-based in DuckDB, 25 seconds. It also no longer treats a sum-of-parts total as rounded on its own (it starts unbounded). Restricted to the old tables' relations it reproduces the earlier baseline exactly (3,739 open and 7,897 closed narrowed, 0 pinned).
  - **Result before live-now counts:** 0 pinned; 13,194 small counts narrowed but not pinned (4,562 open, 8,632 closed), against 11,636 accepted before (+1,558). All are existing code-level cells; no new total is narrowed. By values still possible out of 9: 2 values 59 (57 before), 3 values 929 (870), 4 values 5,227 (5,146), 5 to 8 values 6,979 (5,563).
  - **James, 3 Nov 2026** ("yes accept, carry on with batch B"): the extra mild narrowing is accepted. The check reruns with live-now counts included.
  - **Live now, redesigned:** a live-now table overlapping the quarterly ones (every company live in the snapshot, any registration date) pinned 21 small counts and narrowed 35,280 open ones: a live-now cell shown 0 over four quarters shown 5 forces each to 1. It is replaced by `p_pre2021`, companies registered before 2021 (or with no date) still live, which are different companies from the quarterly cells, so nothing ties them. Live now = before 2021 plus every quarter since, all published cells; the two parts add up exactly. Pin check with it: 0 pinned; 14,152 narrowed but not pinned (5,520 open, of which 958 are before-2021 cells; 8,632 closed), against 13,194 accepted. The extra 958 are on the new table.
  - **Server:** `cover()` picks the fewest published totals (whole divisions, then whole groups, then codes) that add up to exactly the codes asked for; `agg()` sums them and counts cells from shown values and shape only (a council x code or UK x code cell, or a total shown at 50 or more, is one cell; a smaller total is every cell under it), never from which cells are present. The rest of Great Britain is GB's total less the area's, so it carries both their cells. Floors for the at-least-10-for-certain gates still come from the code cells; rank and survival lists also require the tested totals to be 10 or more. Answers with rows carry `PARTS_NOTE` (parts may not add up exactly to the total). New tool `count_companies_live_now`. The area-breakdown total keeps review 5's rule (no range). MEMO.md figures updated (Leeds share 1.48% to 1.40%, was 1.47% to 1.41%; conclusion unchanged) and `scripts/memo_numbers.py` counts cells the batch B way.
  - **Old SIC codes before 2021** (found by `scripts/check_levels.py`: live-now totals for 6 of 11 regions and the UK fell outside narrow ranges): 15,715 companies registered before 2021 (0.6%) still carry one of 430 SIC 2003 codes, which aren't in the code list and don't mean the same (2003's division 51 was wholesale, 2007's is air transport), yet the before-2021 division and 'all' totals included them. They are now left out of `p_pre2021`; the build records the count (rounded to 100) in meta, and live-now answers say so in a caveat. Pin check after: 0 pinned; 13,873 narrowed (5,241 open, 8,632 closed).
  - **Standout lists, a shift against rounding:** with totals rounded once, rank named 15 growth standouts, and one (Westminster, real estate, shrinking, to 2023-Q3) didn't hold on the exact counts (exact z 3.78 against a bar of 3.80; `scripts/check_standouts.py`). Picking the strongest of hundreds of areas favours those whose rounding pushed them over the bar. For the rank and survival lists only (`shift=True`, and `share_change` when `tests` > 1), each count is first moved toward no change by 4 per cell, at most 1 sd of its rounding, before the z is worked out. Growth standouts are then 6, all holding; survival names none. Applied to every answer it cut compare's clear share verdicts from 108 to 51 and the two-area "faster" verdicts from 11 to 0, while single answers had 0 wrong without it, so they keep the old test. MEMO figures are unchanged.
  - **Checks against exact counts (3 Nov 2026):** `check_levels.py` 12,549 ranges, 0 outside (mean half-width: UK about 0.3 to 2.4%, regions 4 to 23%, councils 33 to 101%, live now by region 0.4 to 5%); compare 3,264 answers, 108 clear share verdicts, 0 wrong. `check_regions.py` 1,650 region ranges, 0 outside, and 0 regions further from the sum of their areas than rounding allows; 5,377 quarter rows, 0 outside; 7,633 one-council rows, 1 outside; 411 survival ranges, 0 outside. `check_two_areas.py` 9,640 pairs: "more" 2,627 times, "faster" 11 times, 0 wrong (was 2,503 and 4). `check_breakdown.py` 724 place-settings: 182 division, 12,635 GB and 148 total verdicts, 0 wrong (was 109, 4,693 and 21). Sweep: 9,671 answers including live now, 0 problems. 157 tests pass.
  - **Reviews:** `codex-batch-b.md` PASS WITH FIXES (PARTS_NOTE said every total is rounded on its own), `-v2` PASS WITH FIXES (two README lines; it reran `check_standouts.py` itself: growth 6 of 6 hold, survival none named), `-v3` PASS WITH FIXES (README's fixed test count), `-v4-security` PASS WITH FIXES (no injection, no small count reachable through the tools; pin-check failure messages printed the exact small value they refused, now identifiers only), `-v5` PASS WITH FIXES: four older diagnostics (`check_cases`, `check_standouts`, `truth_cases`, `truth_c`) write exact raw-grid counts, some below 10. Accepted as local-only by design: every report they write is git-ignored, a new test fails if one stops being, the one committed earlier (`truth.md`, Phase C) was removed in Phase D, no remote exists, and the public repo starts from a fresh, scrubbed history. `-v6` PASS WITH FIXES: history also holds `active/review/backfill-check-output.txt` (three UK-wide single-digit counts of rare company types, now shown as "under 10" in the file) and `active/coverage/coverage.csv` (UK quarterly totals only, none under 10). All three paths go on the scrub list for the public history; the scripts also print their reports, so their terminal output stays local. 158 tests pass.
  - **`-v7` FAIL, `-v8` FAIL:** v7 found exact small counts in tracked prose (DECISIONS lines on rare company types and three named areas, and a Phase C review note); they and two tight exact ranges for named areas now read "under 10". v8 found the redaction diffs given to reviewers carry the removed text; those two diffs now live in the git-ignored `active/.tmp/review/`, and redaction diffs go there from now on. Scrub list for the public history: `active/benchmark-c/truth.md`, `active/review/backfill-check-output.txt`, `active/coverage/coverage.csv`, `active/review/diff-batch-b-v7.patch`, and every earlier version of the masked lines. Still to decide before publishing: which working records under `active/` (saved AI answers, e2e runs, another MCP's raw output) go public at all.
- **Public repo leaves out `active/`, 4 Nov 2026** (James: "yep makes sense lets go with the simplest safe option"). `-v9` FAIL found more near-exact small ranges in old review prompts under `active/review/`, after v5 to v8 had found them in reports, diffs and notes there. So the public repo is one fresh commit of the project without `active/` (saved AI answers, e2e runs, benchmark output including another MCP's raw answers, review records, coverage and check reports), and with no earlier history, which carries every earlier version of the masked lines. `active/` and this repo's full history stay local. Publishable set: every tracked file outside `active/`: `src/`, `tests/`, `scripts/` (their reports are written to `active/` when run), `sql/`, `lessons/`, `.claude/`, README, MEMO, SPEC, DECISIONS, CLAUDE.md, LICENSE, `pyproject.toml`, `.gitignore`, `.env.example`, `.aiexclude`, `.cursorignore`. To do when building the public copy: the README's three pointers into `active/` (coverage, AI test, benchmark) and DECISIONS' pointers to review files become plain statements or are dropped, since the files won't be there; CLAUDE.md's two pointers to other local projects (the opportunity-scan verdict and the paused xero-mcp scaffold) are dropped; then a fresh scan of the public tree for small counts.
  - **`-v10` FAIL, `-v11` FAIL, `-v12` PASS** (the publishable set, every tracked file outside `active/`): no small count, secret, salt, company number or postcode in it; 158 tests pass without `active/`. v10 and v11 found setup gaps a fresh clone would hit: the backfill check read a coverage table only `scripts/coverage.py` creates, `scripts/benchmark.py` held a home path, and the build reads the ONS region lookup the README never named. The README setup now covers all of them. Batch B is done; the paid end-to-end rerun is next.
- **End-to-end after batch B, 4 Nov 2026** (`scripts/e2e.py 3`, Sonnet 5.5 client, 24 answers, $0.74): 8/8 on the automatic checks, including new Q8 (how many cleaning companies are in Leeds right now), where all three rounds picked `count_companies_live_now` and quoted its live caveat; the quote check now recognises the live-now summary (an invented one is caught). Q6 (what's growing in Leeds) no longer lists "biggest industries" from rows: the one use of "biggest" quotes the server's warning against it. Median 252 words (256 before); Q4 runs longest (435). Previous answers kept in `active/e2e/before-batch-b/`.
- **Largest lists, 4 Nov 2026** (agreed in the user-review plan: "a plain 'biggest areas by count' list, with ranges and no claim of significance, would answer 'where are most X startups?'"). Two tools: `largest_areas(sic_codes, level council|region, period, include_closed=True, limit)` and `largest_industries(area, period, include_closed=True, limit)`, by 2-digit division. Rows are in order of rounded count, listed only with at least 10 for certain (code-level floors, as elsewhere) and numbered, each with its likely range and a likely rank: best is 1 plus the rows whose likely range lies wholly above, worst is the rows whose range reaches its low end, over every candidate, listed or not. Overlapping rows share a span (e.g. "1–2"), so no order is claimed between them; a single rank does claim one. An unnumbered candidate counts up to the top of the likely range `release()` would give it: the hard bound (4 per cell) let a Leeds division shown under 10 over 288 cells outrank retail, so every rank said nothing. Nothing new is released: every value is a sum of published totals. New `period()` (one period, shared with `window()`) and `div_floors()` (shared with the breakdown). Instructions point "where are most" and "biggest industries" here, and say never to order places or industries from separate answers.
  - **Against exact counts** (`scripts/check_largest.py`, 32 industries by council and region; 40 random councils, 11 regions and nations and the UK by division; open and including closed): 3,936 listed rows, 0 ranges outside, 0 likely ranks without the exact rank, and all 328 single ranks right. Mean span: regions about 1 to 2 places, councils about 36 to 57 (single codes over 350 councils are mostly within chance of each other).
  - **Sweep:** 10,751 answers (largest_areas for every code, largest_industries for every council, three new refusals), 1,080 lists in count order with valid spans, 0 problems. The small-count scan flagged likely ranks "1" and "2" as counts; only the exact field `likely_rank` is exempt, with a test that any other field holding a small number is still flagged. 161 tests pass. e2e gains Q9 (where are the most new AI companies) and Q10 (biggest industries in Leeds), and its quote check recognises both summaries.
  - **Review** `codex-largest.md` PASS WITH FIXES: (1) a single "likely rank 1" could read as certain, since the caveat isn't in `answer`: both summaries now say even a single rank is an estimate from rounded counts, not certain, and so does the README. (2) The check covered one period: it now runs three (latest year, 2026-Q3 alone, 2022) and three sparse code mixes, 11,476 listed rows, 0 ranges or likely ranks wrong, all 853 single ranks right. A list of 25 single ranks still carries a multiple-comparison risk (each range is pointwise); none failed in the sample, and the README calls the check a sample, not a guarantee. 161 tests pass.
  - **End-to-end with the lists, 4 Nov 2026** (`scripts/e2e.py 3`, 30 answers, $0.95): 10/10 on the automatic checks; Q9 (where are the most new AI companies) and Q10 (biggest industries in Leeds) picked `largest_areas` and `largest_industries` in every round. Read by hand: clients kept the spans ("Birmingham and Westminster lead, and the data can't separate them"; "tied for first, each with likely rank 1–2"), mostly stated an order only where a single rank gave one (London first, the South East second) and said overlapping rows could go either way. Two exceptions, found by review `codex-largest-v3.md`: round 1 of Q9 put overlapping council areas in sequence (Manchester "next", the rest "follow") and called the leading pair "tied for first", which rounded counts can't show; round 2 had overlapping regions "follow" in order. Q9 and Q10 run long (median 377 and 411 words). Batch B's run kept in `active/e2e/after-batch-b/`. Review `codex-largest-v2.md` PASS WITH FIXES (the check's header said 32 industries, now 35 selections).
  - **Review `codex-largest-v3.md` PASS WITH FIXES, and the fix, 5 Nov 2026.** (1) Clients ordered rows whose spans overlap (above). Both summaries now say overlapping rows could be in either order "(none comes before another, and a tie can't be shown)", and the instructions say to keep such rows together as a group in any order, never saying one is next, follows or is ahead of another, and never calling them tied. `scripts/e2e.py` flags list answers that use ordering words (next, follows, ahead of, behind, tied and so on) outside a real quote of the server. It is a flag to read by hand, not part of the gate: "follow" is right after a pair whose span lies wholly above the rest. (2) The record above no longer says clients ordered rows only by single ranks; it keeps the old "tied for first" as a quote of the failure. 162 tests pass. **End-to-end rerun** (`scripts/e2e.py 3`, 30 answers, $0.94): 10/10. One answer flagged, r1q9 ("Manchester, Tower Hamlets, ... follow in a wide overlapping group ... so I can't order them", after Birmingham and Westminster at 1–2): read by hand, it is correct, since no listed rank below the pair reaches 1–2. The other five list answers kept overlapping rows as a group, and none called rows tied. Median words: Q9 441, Q10 406. The previous answers are kept in `active/e2e/largest-v1/`.
  - **Review `codex-largest-v4.md` PASS WITH FIXES, 5 Nov 2026.** (1) r2q10 said the formation-agent share was of "Great Britain's companies registered in this period", dropping the summary's "with these codes". Checked: for `largest_industries` the codes are all 731, including no activity stated, so the two are the same set and the answer is right; no change. (2) The record's wording about "tied" was unclear; it now says the record was corrected and keeps the old quote. (3) The flag missed "leads", "tops", "ranks above" and "beats", and an invented quote holding any fragment of the raw tool results could hide an ordering word. The word list now has them. Before the scan, a quotation made only of whole sentences from one served summary or caveat is taken out, and so is any whole served sentence outside quotation marks; a quotation that isn't wholly served is scanned in full, even where it holds a served sentence (review `codex-largest-v6.md`), and a fragment of a served sentence is not exempt. "Comes before" is scanned except in the summary's own "none comes before", which clients reword around its semicolon (keeping the whole phrase out of the list flagged three correct answers and missed "Manchester comes before Leeds", review `codex-largest-v5.md`). Rescored: still 10/10, and only r1q9 is flagged, which was read by hand above. 162 tests pass.
  - **Reviews `codex-largest-v5.md` and `-v6.md` PASS WITH FIXES, `-v7.md` PASS, 5 Nov 2026.** v5: "comes before" back in the flag, with only the summary's own "none comes before" exempt, and the exemption described as built. v6: an invented quote holding a served sentence hid it from the scan; a quotation is now exempt only when it is wholly served, otherwise scanned in full, with a test. v7 tried each case (whole quote, invented quote, fragment, unquoted served sentence, curly and straight quotes) and found nothing. 162 tests pass; e2e rescored 10/10, only r1q9 flagged and read by hand. The largest lists are done.

## 5 Nov 2026: Batch C, closures by dissolution date
- **What it is for:** the user reviews' "are more businesses opening than closing in Leeds?" and "are restaurants closing faster than they open?". No tool counts closures in a period; `include_closed` only says how many of the new companies have since closed. James approved a full closures download on 3 Nov and said "go batch c" on 5 Nov.
- **`scripts/backfill_closures.py`:** every company dissolved from 2021-01-01 to 2026-09-30, whatever year it was incorporated, one dissolution day at a time. It stops at the last quarter both openings and official figures cover. Every row comes from this download, so the build won't merge two sources, and the earlier closed data becomes a cross-check by company number. `get()` is shared with `backfill_closed.py`, which behaves as before.
- **Big days are split, not paged.** Strike-off days can pass the 5,000 page size and the API states no limit on paging depth, so a big day is split by incorporation date until each part fits. Parts must add up to the day's hits.
- **Nothing incomplete is marked finished.** A day that doesn't add up after 3 tries, or holds repeated or blank numbers, isn't saved; the run carries on and exits 1 naming it, and a rerun retries it. Finished days are checked again on resume. A row with the wrong dissolution day stops the run.
- **Reviews:** `codex-closures-download.md` FAIL (shortfalls accepted, resume trusting a line count, hits moving mid-day), fixed. `-v2.md` FAIL (blank numbers could be saved; an empty 404 could hide a day), fixed: an empty day is asked twice. `-v3.md` PASS WITH FIXES, two notes accepted without change: a day empty on both asks stays unproven until the quarterly match to official dissolutions passes, which is the next step and the gate for the whole download; and resume reads each day file whole, so memory is bounded by the largest day. 164 tests pass here; Codex's read-only sandbox couldn't run them.
- **The run (James, 5 Nov):** 2,099 days, 3,888,012 companies, none incomplete. `scripts/closures_check.py` passes: every day whole, no company twice, 0 also in the snapshot, 63 of the earlier backfill missing here, no strike-off Tuesday empty. Against official Dissolutions the download is 29,619 short of 3,887,362 (0.76%), inside the 40,850 official restorations. From 2022-Q2 every quarter is 0.38-1.23% short. Earlier quarters swing from -5.06% to +7.89%, which fits batches falling either side of a quarter end (consistent, not proven).
- **The official line is Dissolution, not Struck off.** The first check used Struck off, and I told James June's low figure was a dissolution figure. It was an outage pause in strike-offs, not closures: dissolutions were 42,819 in June and 92,208 in July.
- **Tables:** `grid_gone`, `p_uk_gone`, `p_area_gone`, `p_mass_gone`, `p_agg_gone`: same rounding to 5, types, lookup and agent flag as the rest, by dissolution quarter. Pin check on 2,445,754 cells: 0 pinned, 0 UK cells repaired. 4,510 companies with old 2003 codes are left out.
- **Tool:** `registrations_against_closures`. Registered uses open plus closed, so registrations aren't shrunk by closures. Default four quarters. **Under a year gets counts but no verdict:** on exact counts (`scripts/check_closures.py`, 35 selections, 54 places) the side with more flips in 1,113 of 3,701 moves from one quarter to the next, against 629 of 6,670 when a year's window moves on by a quarter, and of 5,106 clear years only 24 are clear the other way a quarter later.
- **Exact-count check:** 11,130 figures, 3 outside their likely range. 1,450 clear verdicts, 0 the wrong way. 167 figures of 10 or more show as 'under 10 (rounded)', the known effect of adding several rounded cells (case C7); `SMALL_NOTE` says the true count may be higher.
- **Area verdicts allow for the addresses left out.** The two sides leave out different shares, so a close area verdict could be an artefact: in the latest year 24.0% of registrations and 22.2% of closures are at agents' addresses, and 6.1% of closures are at Companies House's default address (CF14 8LH, flagged as agents). An area's verdict must survive each side being scaled back up at Great Britain's rate for those codes. That stopped 63 of the 1,513 verdicts in the check, and the summary says why. It is an estimate, because nobody knows where those companies really are.
- **Addresses that pile up closures:** 1,821 postcodes not flagged as agents hold 493,907 closures at 100 or more each. In the latest year that is a median 8% of a council's closures, and 20% or more in 41 of 357 councils. These may be liquidators' or shared offices, unproven, so it is a caveat rather than an adjustment.
- **Across families (corrected by the privacy review):** I first argued the only link was closed <= closures + October, with October unpublished. Wrong: a company dissolved within a year of registering is in closed under_1y at its registration quarter and in closures within the next four quarters, so for registrations up to 2025-Q3 October can't loosen it. `codex-closures-privacy.md` found this narrowed 2,255 small council x code cells from `serve.duckdb` alone, with no exact count recovered. `build_levels.links` now checks closed and closures together at every level, over every run of quarters: 286,886 limits that could bind, 0 pinned, 15,856 small cells narrowed against 12,462 with the two checked apart. The limits need a company to sit in the same cell in both downloads: of 1,947,204 in both, 17 changed postcode and none changed first SIC, type or dissolution date (`closures_check.py`), and 63 of the earlier download dropped out of this one. So a limit isn't true of every cell: it can be loose by those companies. The check treats it as exact, the client's best case. Propagation is monotone, so stricter limits only give narrower ranges: anything pinnable under the real limits shows as a pin or an empty range, and both stop the build. The 15,856 narrowed may overstate slightly; 0 pinned stands. Narrowed is the residual this project already accepts for overlapping rounded tables; pinned fails the build. The whole-period link with October stays as measured: over 122,198 council x code totals the closed lower bound equals the closures upper bound in 0 and passes it in 2 (both real October closures).
- **Reviews:** `codex-closures-tool.md` PASS WITH FIXES (0.8% caveat stated too broadly, flip rate compared across gaps, an empty range skipped by the check), fixed. `codex-closures-privacy.md` PASS WITH FIXES (above), fixed. `codex-closures-v3.md` PASS WITH FIXES (same-cell assumption unmeasured, ties counted as flips), fixed. `codex-closures-v4.md` FAIL (the limits were stated as true of every cell, which those companies break): reworded above, limits kept as the client's best case rather than rebuilt, because no published cell needs to change. `codex-closures-v5.md` PASS WITH FIXES (accepted that argument; the tool was described as if it could show closures speeding up, and the 0.8% caveat had no period), fixed. `codex-closures-v6.md` PASS.
- **End to end (paid, $1.14):** 12/12 over 3 rounds, with the new Q11 (Leeds) and Q12 (restaurants) both picking the new tool every round. Latest year: Leeds about 7,835 registered against about 7,075 dissolved; UK restaurants, cafés and takeaways (561) about 36,490 against about 33,235. One Q11 answer said the two likely ranges overlap at the edges; they don't. That is the client's own sentence, not served text.
- **Left-out figures kept apart (tidied after the run):** an area answer gave one 'couldn't be placed' figure, from open and closed companies, and one formation-agent figure that added registrations and dissolutions, which counts a company twice if it did both in the period. It now gives each side its own: for Leeds about 550 registered and about 670 dissolved at agents' addresses, and, of companies at other addresses in Great Britain, 0.21% of registered and 0.38% of dissolved not placed. I first gave the closures figure as 0.48%, then 0.31%: 0.48% counts unmatched postcodes at agents' addresses too (0.31 + 0.17 on exact counts), and 0.31% kept the UK total as its base, including agents and Northern Ireland, which area answers leave out. Other tools keep their existing figure. `codex-closures-v7.md` PASS WITH FIXES: the two shares are for the whole dataset, not the question's selection, so the caveat now says so; and a formation-agent figure shown as under 10 now brings its note. `codex-closures-v8.md` PASS WITH FIXES: the share's top and bottom covered different companies, fixed as above. `codex-closures-v9.md` PASS WITH FIXES: a new `unmatched_dissolved_pct` field was misdescribed and put a null in every other tool's output, so it is gone: the structured `unmatched_pct` holds the registered share and the must-quote caveat holds both. `codex-closures-v10.md` PASS WITH FIXES: the field's description now says so.

## 5 Nov 2026: final review with fresh reviewers (James: "do a final review and testing with fresh memory")
- **Before it:** review v11 of the batch C tidy-up passed, at b4e6cb9. Tests 168, sweep clean, both closures checks unchanged.
- **Round 1:** Codex PASS WITH FIXES. A fresh outsider, calling every tool and comparing answers, FAIL: verdicts true to the sums but wrong for the reader, on older tools that earlier reviews had checked one change at a time.
- **The ranking was mostly measuring closures (fixed).** It ranked on still-open counts, and areas that lose more older companies look like they're growing. `scripts/check_rank_basis.py`: 89 selections, four periods, both directions. On still-open counts it named 32 areas: 11 held on exact counts with dissolved companies, 3 went clearly the other way. With dissolved companies counted it named 39, and all 39 held. Earlier exact-count checks passed because they used the same live-only basis. `rank_areas_against_great_britain` now counts dissolved companies by default. **Cost, for James to know:** the latest period names no area in that check (11, 10 and 18 in the three older ones), because recent closures are thin and noisy. The answer says the test is cautious.
- **No verdict where closures or the season can explain it.** A quarterly trend on still-open counts, or between different times of year, gets no verdict. The first quarter was the busiest in four of the five years from 2021 to 2025 (the script prints it; I first wrote "every year" from reading a table by eye, and the script corrected me). `breakdown_by_industry` with `previous` across seasons tests nothing and says why.
- **Closures verdict:** must also hold with the area's own left-out addresses put back, not only at GB's rate. Wales left out about 46,000 dissolved companies against about 17,000 counted. Clear verdicts 1,450 to 1,378, 0 the wrong way, 135 held back (was 63).
- **Wording that was false or misleading, fixed:** "grew faster" of a place that fell, now "fell less"; "this data can't check that", which it can; Great Britain's total now says it leaves out formation-agent addresses; the left-out figure says when it covers both periods; "survived their first year" is now "weren't dissolved in their first year"; "rounded to the nearest 5" now says the figures are randomly rounded; division 98 is residents property management; the README's 2 million was registered since 2021 and later dissolved, not all dissolved since 2021 (3.9 million).
- **`find_area`:** matches from the start of a word, takes everyday spellings, and explains an empty result. "GB" had found Rugby, and "England" East of England.
- **Ranges:** every tool's low end with dissolved companies counted stays at or above the still-open low end, and a total stays at or above the sum of its parts' low ends. A range reaching 0 is flagged low.
- **Also:** answers from a snapshot over 45 days old say so (Codex raised stale data twice). Long bad codes are cut, catch-all codes say so, lists say when rows are cut, survival ranges are as precise as the rate.
- **Known limits, left as they are:**
  - Recent periods with dissolved companies counted have wide ranges and a cautious test. A small closed total counts every cell under it. The tighter cap failed review on 2 Nov (1,852 counterexamples), so it stays, and the answer now says so.
  - Unmatched postcodes aren't put back in the closures verdict: 0.21% against 0.38%, in a must-quote caveat.
  - `find_sic` near-misses ("film", "school", "nail bar", "crypto"), the location quotient has no test, and councils merged since 2021 aren't mapped to their successors.
  - Wrong-type inputs return the MCP library's validation message.
- **Rounds:** Codex 1 PASS WITH FIXES, outsider 1 FAIL; Codex 2 PASS WITH FIXES, outsider 2 PASS WITH FIXES; Codex 3 PASS WITH FIXES (a flat count called "grew faster", fixed: "held steady while the other fell"); Codex 4 PASS on that fix. Reviews are in `active/.tmp/` (`codex-final*.md`), git-ignored.
- **Final results at c5226a5:** tests 193 pass. Sweep 12,181 answers, 0 problems. End to end 12/12 over 3 rounds ($1.21); answers in `active/e2e/`, the previous run in `active/e2e/after-batch-c/`.
- **Exact counts:** closures 1,378 clear verdicts, 0 the wrong way, 135 held back by the address guard, 3 of 11,130 figures outside their range (run at 7b052e5; c5226a5 changed only one sentence in `compare_two_areas`). Ranking 39 of 39 hold, 25 of 25 at division level. Two areas 9,640 pairs, 0 wrong. Largest lists 11,476 rows, 0 outside. Breakdown 5,510 verdicts, 0 wrong. Levels 12,549 ranges, 0 outside, 108 share verdicts, 0 wrong way. Regions 1,650 ranges, 0 outside.
- **One slip left in the end-to-end answers:** r3q9 says the other regions "follow" and calls Wales "the smallest", which the instructions tell clients not to do. The order-word check is read by hand and isn't in the SPEC gate. Quoting a summary word for word: 1 of 36, also not in the gate.
- **Ranking in the latest period (James, 5 Nov 2026):** accepted. It stays on counts with dissolved companies even though it will often name no area for the latest period: "yeah im fine with that if thats what the data points to". No tighter closures table for now.
- **Survival agent-share check, 5 Nov 2026 (open since batch A; James: "yeah go"):** it flips often. `scripts/check_survival_agents.py`, exact counts, five cohorts, all industries, divisions and 5-digit codes, each area against the rest of Great Britain, agents left out then put back on both sides. Of 749 clear single-area verdicts, 220 changed (29%), 19 of them reversed. At the list bar, 30 of 144 (21%), 1 reversed. By group, 15-26% changed where agents are under 20% of GB's companies and 28-39% at 20% or more. Many more verdicts appear with agents in (up to 495 in one group), so agents-in isn't the truer answer: agent addresses say little about the area. Agent-address companies also behave differently: not dissolved in their first year 87.6% against 96.5% for the 2024 cohort, though 97.0% against 96.6% for 2021.
  - **Scope (review `codex-survival.md`, FAIL, fixed):** council areas only, on exact counts without the tool's rounding allowance, and overlapping tests. My first wording put "2 to 3 in 10" into every clear answer, including regions, custom periods and lists, none of which were measured.
  - **Change, as agreed before the run:** a warning, not a new verdict rule. A clear survival verdict, for one place or a list, now says it can change when those addresses are put back and that it describes companies at other addresses, with no figure. A verdict that isn't clear gets the existing `agent_warning` at 20% or more.
  - **Not done:** holding a verdict back as the closures tool does. James can ask for that.

## 5 Nov 2026: code audit before publishing
- **Result:** no critical findings. No tool call can reach a paid or outside service, and no tool has an uncapped loop or query. All findings are in `AUDIT-FINDINGS.md`, and `scripts/measure_tools.py` repeats the measurements over real stdio.
- **Fixed:**
  - **`NO_DATA`:** a missing or unreadable data file, or one with tables missing, gave `INTERNAL`, which told agents to try again. Every fresh clone starts with no data, so `db()` now checks for all 18 served tables and says so. Nothing is cached on failure, so a built file works with no restart. A test ties the list to `export_serving.SERVED`.
  - **README:** restart after a rebuild, every place dates are fixed, and which scripts matter.
- **Left as they are (notes):** the size of the tool list and of each answer; no overall cap on hand-run AI tests, which the README states.
- **New working rule, James:** Codex routinely checks Claude's work, so a fresh read-only session runs after the findings, after each batch of fixes and before hand-off. Added to the `code-audit` skill as part of its exit condition.

## 5 Nov 2026: James's decisions before publishing
- **Northern Ireland, James: "identify those companies by the BT prefix":**
  - **Why:** ONS says commercial use of its Northern Ireland postcode data needs a separate licence. The build no longer loads those rows, and it fails if any reach the lookup.
  - **What changed:** a company is in Northern Ireland if its own register postcode starts BT and a digit. All those companies share one code, `N92000002`, so the 11 council rows are gone. No tool ever served them.
  - **An improvement it brought:** 2,894 of the lookup's 63,293 BT rows had no council code, so those companies counted as unmatched and in GB. `active/check_bt_switch.py` compared the two builds. Northern Ireland rose by 872 quarterly live, 352 pre-2021 live, 6,692 closed and 6,739 closure companies.
  - **What stayed the same:** every total, every UK figure and every GB council row. Served rows changed only for the unmatched area and GB totals.
  - **Same snapshot:** the old build was never public, so this rebuild doesn't raise SC-12. Any other snapshot file is now refused, by SHA-256, until the two-snapshot check exists.
- **Who built it, James: "built by James [with] Claude Code":** the README says James set the direction and made the decisions, Claude Code wrote the code, tests and documents and ran the checks, and Codex reviewed independently. `CLAUDE.md`, `SPEC.md` and `check_query.py` now agree. The first query's own header already said Claude wrote it.
- **Rival projects, James: don't name them:** they're now MCP A, B and C here, and `cases.py` calls them `ch`, `mcp_b` and `mcp_c`. Old result files keep their private names.
- **Agents with a shell, James accepted the Cloudflare item:** `benchmark.run()` now refuses any agent with shell access, so those comparison runs can't be repeated until that access is restricted. Web and Market Pulse agents still run.
- **Public commit email:** the GitHub noreply address, used on the fresh public commit only.
- **Licence name, James, 6 Nov 2026:** `LICENSE` says Temi Oyemade.
- **Publishing order, James, 6 Nov 2026:** GitHub's secret and code scans are free only on public repos for a personal account, and CodeQL's licence excludes local use on code that isn't open source yet. So the second opinion before publishing is local: an exact-value search for both secrets, TruffleHog and Semgrep. Then an empty public repo gets the one push, so GitHub's push check applies, and the link isn't shared until GitHub's own scans are clean.
- **Required scans:** `.github/workflows/scans.yml` runs gitleaks, Semgrep and osv-scanner. The two `nosemgrep` comments cover only the accepted MS-10 lines. Tests can't run there, because the data isn't in the repo.
