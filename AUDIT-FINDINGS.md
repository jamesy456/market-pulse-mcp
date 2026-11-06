# AUDIT-FINDINGS

Shared by `code-audit` and `security-checklist`. Append only.

| id | skill | area | severity | evidence | status | test |
|---|---|---|---|---|---|---|
| CA-1 | CA | dependency failure | should-fix | Missing, empty, junk, half-written or table-less `serve.duckdb` answered "INTERNAL: the query failed; try again or simplify it" (drill), and a file with `meta` but missing tables would have too. Every fresh clone starts with no data. `src/server.py` `db()` | verified | `test_audit_broken_data_file_says_so_and_recovers` failed 5 of 5 before the fix, passes 5 of 5 after; `test_audit_old_or_partial_data_says_so_to_every_first_caller` (8 parallel first calls over a client) failed before, passes after; `test_audit_required_tables_match_the_export`; `test_audit_every_tool_says_no_data_and_shows_no_path` (all 12 tools over a client); drill rerun |
| CA-2 | CA | dependency failure | should-fix | A running server keeps its open connection after a rebuild: the drill's replaced file still served the old snapshot date. README didn't say to restart | fixed | README step 4; the behaviour itself is unchanged |
| CA-3 | CA | chatty | note | `tools/list` 36,846 bytes (inputSchema 14,675, outputSchema 16,315, descriptions 5,891). Each answer is carried as text and as structured content, and `answer` repeats the summary and two caveats, kept because agents need one field to quote. Biggest answer 130,581 bytes, only when asked for every area | not changing | `scripts/measure_tools.py` |
| CA-4 | CA | runaway cost | note | No overall cap on hand-run AI tests: `e2e.py` is $1 a question, so 12 questions over the default 3 rounds is at most $36 (the last full run cost $1.21). `benchmark.py`, `benchmark_c.py`, `cases.py` and `breakit.py` are also per-run limits times the rounds asked for. No tool call can reach them | not changing; README says so | Codex call-chain check |
| CA-5 | CA | resources | note | Long-running server keeps one connection and one cursor per worker thread; no file writes and no growing state found, peak memory 169 MB in the measured run. No long-duration test was run | not-tested | Codex check; `scripts/measure_tools.py` |
| CA-6 | CA | public repo | should-fix | Refresh note named only `build_grid.py`, but dates are also fixed in `backfill_closed.py:27`, `backfill_closures.py:30`, `coverage.py:12-14`, `backfill_check.py:23`, `closures_check.py:25-26` and the check scripts | fixed | README lists them and gives the search command |
| CA-7 | CA | public repo | should-fix | A stranger couldn't tell which scripts are needed: at 17894ac, 18 of 39 had no mention in the README, CLAUDE.md, other scripts or tests | fixed | README "What's in `scripts/`" |
| CA-8 | CA | public repo | note | `.env.example` called the Companies House key "not needed in v1", which was out of date | fixed | `.env.example` |
| MS-1 | MS | schemas | should-fix | Unknown fields were dropped: `to_quater` answered for the default period with no warning, and no schema set `additionalProperties: false` | verified | `test_security_a_misspelt_option_is_refused_not_ignored` failed before, passes after |
| MS-2 | MS | tool surface | should-fix | No record of the reviewed tool definitions, so a changed description or annotation could pass unnoticed | verified | `test_security_tool_definitions_are_what_was_reviewed` with `tests/tools.sha256` |
| MS-3 | MS | logging | should-fix | Only failures were logged. Each call now logs tool, outcome, time and field names to stderr, never values | verified | stdio test with canary secrets: failed before, passes after |
| MS-4 | MS | supply chain | should-fix | No lockfile: only 3 of 34 packages were pinned | verified | `requirements.lock` with hashes; clean install passes all 211 tests; `pip-audit` and `osv-scanner` clean |
| MS-5 | MS | publishing | should-fix | No `SECURITY.md`, and the README didn't say what the server reads, writes and connects to | fixed | `SECURITY.md`; README "What it can touch" |
| MS-6 | MS | outputs | note | `find_area` echoed up to 40 unescaped characters of input; other tools echo 12 escaped ones | verified | `test_security_hostile_text_is_refused_cleanly_everywhere` failed before, passes after |
| MS-7 | MS | logging | note | An unexpected failure logged its inputs at any length; now cut to 300 characters | fixed | `src/server.py` `coded` |
| MS-8 | MS | schemas | note | `area`, quarter and code strings have no length cap in the schema. A 100,000-character value in each is refused cleanly and its echo is cut | not changing | hostile test |
| MS-9 | MS | outputs | note | A wrong-type input returns the validation library's message, with a fixed link to its docs and a cut piece of the input. The README mentions these messages | not changing | hostile test keeps it under 10,000 characters |
| MS-10 | MS | code scan | note | `semgrep` flagged 2 dynamic `urllib` calls. Both URLs start from the fixed `https` constant in `scripts/closed_check.py:17`, and neither script is reachable from a tool | accepted | `scripts/backfill_closed.py:45`, `scripts/closed_check.py:36` |
| MS-11 | MS | tool surface | note | `instructions` use "always" and "never". They are visible, stay within this server's own answers and carry the privacy and accuracy rules, so they stay | accepted | test: ASCII only, no markup or links |
| SC-1 | SC | public repo | medium | Tracked `DECISIONS.md` and two test comments gave real counts below 10, from old bug reports. Found by the Codex attacker and the security engineer | fixed | grep for the patterns finds none in `src/`, `tests/` or the rewritten `DECISIONS.md` lines |
| SC-2 | SC | logging | low | The README said searches never log what was typed, but the SDK logged refused input at INFO | verified | stdio test with a no-match search failed before, passes after |
| SC-3 | SC | hardening | note | Connection settings weren't locked, and auto-install was on though blocked by another setting | verified | `test_security_the_connection_cannot_write_or_reach_outside` failed before, passes after |
| SC-4 | SC | secrets | note | `.env.*` wasn't ignored, and the README didn't tell users to protect `.env` | fixed | `git check-ignore -v .env.local`; README step 2 |
| SC-5 | SC | public repo | low | `CLAUDE.md` held local paths and a username | fixed | no `/Users/` left in the public tree; other `CLAUDE.md` wording is for James (see below) |
| SC-6 | SC | wording | medium | README overstated: "handles all four", "don't get lost", an unsourced ONS comparison, "pinned" as if proved, 5.6M rows (5,711,779 in the spike) | fixed | README lines; no statement left that the pin check is a proof |
| SC-7 | SC | wording | medium | README left out dormant companies, self-chosen codes, company types, and checking the original sources | fixed | README "What it will not do" and the disclaimer |
| SC-8 | SC | licence | medium | Licence basis was a 2021 forum post, and the region lookup and statistics had no attribution | fixed | GOV.UK wording read 5 Nov 2026 (page updated 25 Oct 2022); README cites it |
| SC-9 | SC | wording | low | `MEMO.md` put "booming" in quote marks with no source; the council's page doesn't say it. The "over 3,000" quote is on that page | fixed | council page read 5 Nov 2026 |
| SC-10 | SC | public repo | note | Fake fixture rows use real postcodes, one named `DECISIONS.md` line used a postcode (now removed), and `check_closures.py` names the Companies House default address | accepted | rows are named FIXTURE COMPANY; the address is public |
| SC-11 | SC | privacy | note | The pin check is sound but not exhaustive: on made-up tables a fuller search beat it for 6 small cells in about 22,500 tables, never reaching one value. A sample of the real tables showed no gap | accepted; README says it's not a proof | attacker's report; not re-run by me |
| SC-12 | SC | privacy | to-do before first new snapshot | The cell key has no snapshot term and the salt never changes, so a client keeping answers from two snapshots sees the same rounding step as counts move. No check models this. Only one snapshot is served today, and the Northern Ireland rebuild used the same snapshot | open, snapshot blocked in code | `build_grid.py`, the only script that reads the snapshot into the grid, refuses any file but the served one, by SHA-256, until a check simulates two snapshots. New closed-company downloads aren't blocked in code but change counts too, so the README says not to publish a rebuild from them, and that check must cover them |
| SC-13 | SC | James | decision | Who built it, naming rival projects, Northern Ireland licence, git identity: see "Decisions for James" | fixed | all four decided 5 Nov 2026 and applied; `git grep` finds no rival name in the public tree; Northern Ireland check below |
| CF-1 | SC | test scripts | accepted | Cloudflare `needs_validation`: `benchmark.run()` gave agents shell access while they read register text, which could steer them to `.env` or raw data. Only the hand-run scripts are affected, not the server | accepted by James, blocked in code | `run()` refuses any agent with Bash; `test_agents_with_a_shell_are_refused` |
| MS-12 | MS | publishing | to-do at publish | Turn on private vulnerability reporting, tag a release, and add scans as a required GitHub check. Publish one fresh commit of every tracked file outside `active/`, with no history: `.gitignore` doesn't cover `active/`, so a plain push would publish it | open | not possible before the repo exists |

**Rejected after checking:**
- Codex scope check: DECISIONS phase D says the export has six protected tables, while `SERVED` now has more. Not changed: it is a dated record that was true on 2 Nov, and the README and `SERVED` are current.
- Codex scope check: "11 tools". The server registers 12 (`grep -c "^@mcp.tool" src/server.py`).
- First simulated public tree: 2 of 200 tests failed. Neither is a bug. One needed `active/coverage/coverage.csv`, which README step 3 creates, and one needed a git repo. With both in place, 200 pass.

## MCP security review (Profile A: stdio, read-only, no network, public data)
- **Sections 1-5, 8, 9:** run. Sections 6 and 7 don't apply: no HTTP, and no spending.
- **Secrets:** `gitleaks` found nothing in 129 commits or in the 66 files that would be published. The server reads no environment variables. `.env` and `data/` are ignored, proved with `git check-ignore`.
- **Inputs:** 15 hostile strings through every text argument of every tool: none gave `INTERNAL`, ran a command or changed data. All SQL values are parameters. Table and column names come from fixed values in the code.
- **Connection:** tests confirm writes, `COPY`, `read_csv`, `ATTACH` and `INSTALL` are refused.
- **Outputs:** no free text is served. Every label is checked as plain short text with no markup or links.
- **Fixture:** `tests/fixtures/snapshot_sample.csv` is 200 fake rows from `scripts/make_fixture.py`.
- **Not run:** the optional fuzzers and `snyk/agent-scan`, which needs a Snyk token and sends data to Snyk. No package is built: this isn't published to PyPI.

## Security panel (Stage 2), four separate reviewers at 5c71b71
- **Security engineer:** PASS WITH FIXES. All 5 f-string queries use constants or allow-listed names; about 60 hostile values gave no error; a Python audit hook saw no sockets, subprocesses or writes.
- **Risk and compliance:** PASS WITH FIXES. No emails, session IDs, secrets or real company numbers.
- **Attacker (privacy, tools only):** PASS. No count below 10 or company-level fact recovered. Sampled, not the full grid: closed and closures tables were read, not scanned.
- **Codex attacker:** PASS WITH FIXES (SC-1). It found no tool path to a small count, secret, file or code execution, and said that isn't proof none exists.

## Decisions for James
- **Who built it:** README says "Built by James" and `CLAUDE.md` says James writes the core pieces, while `DECISIONS.md` records Claude writing them. `lessons/` is empty.
- **Named rival projects:** `DECISIONS.md` and `scripts/cases.py` name GitHub projects marked down in tests whose evidence stays private.
- **Northern Ireland:** ONS says commercial use of BT postcodes needs a separate licence. Identifying them by the BT prefix would avoid the lookup.
- **Git identity:** past commits use a Mac-hostname email; the public commit needs a GitHub noreply address.

James decided all four on 5 Nov 2026, and `DECISIONS.md` records them.

## Scans and outside audits
- **Scans at d2a8fbb:** `gitleaks` found no leaks in 129 commits or 66 public files. `pip-audit` and `osv-scanner` were clean on 34 packages. `semgrep` gave 2 false positives, both a fixed https URL.
- **Cloudflare `security-audit` at d2a8fbb:** 0 confirmed, 1 `needs_validation` (CF-1, accepted), 7 rejected. No target code ran. Report: `~/security-audit-skill/market-pulse-mcp/run-1/`.
- **Strix:** skipped. It needs a paid AI key, is built for live web apps, and would get write access to its folder. This server has no web surface.
- **End-to-end:** 12 of 12 questions passed, 3 of 36 answers word for word, $1.17.

## Handover gate
| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Secrets out of code | PASS | gitleaks above; `.env` and `.env.*` ignored; `.env.example` has names only |
| 2 | Errors logged with time and intent | PASS | `coded` in `src/server.py` logs each tool, outcome and time to stderr, and full detail for unexpected failures; the database opens through `db()`, which logs failures. Download scripts report failed days and can resume |
| 3 | Told straight away when it breaks | NOT APPLICABLE | Nothing runs unattended: the server starts on demand and every failure goes back to the caller |
| 4 | Paid API caps | PASS | No tool reaches a paid API. The AI test scripts have a limit per run but no overall cap (CA-4, stated in the README) |
| 5 | README for a non-technical reader | PASS | "What you can ask", "For whoever runs it", "When something goes wrong" |

- **Indexes:** none needed. Slowest of 12,181 sweep answers was 0.45 s.
- **Rollback:** not tried. Nothing is deployed; going back means restoring the previous tagged release and its `serve.duckdb`.

## Security checklist, stage 1
This is a local stdio server with no web surface, accounts, forms or personal data, so most categories can't apply.

| Categories | Result | Why |
|---|---|---|
| 1 Login, 2 Access control, 3 Sessions | Not applicable | No users or accounts. The caller is the local process that started it |
| 4 Secrets | PASS | Environment file ignored; agents denied it in `.claude/settings.json`, `.cursorignore` and `.aiexclude`; git history scanned. The server doesn't need the API key. No build output exists |
| 5 Input validation | PASS | Typed tool inputs, unknown fields refused, hostile text tested (`test_security_*`) |
| 6 XSS, SQL injection, CSRF | PASS for SQL | Values are bound parameters, and the 5 f-string queries use constants or allow-listed names. No web pages, so no XSS or CSRF |
| 7 Encryption | Not applicable | Public data on the user's own disk, and no network. The salt stays in `.env` |
| 8 Rate limits and cost | PASS | No metered call from a tool. Input and row caps are in Results; the Companies House downloads keep to the published limit |
| 9 Endpoints, 10 CORS and headers, 13 Bots | Not applicable | No HTTP endpoints, uploads, admin routes or forms |
| 11 Production settings | PASS, rollback not tried | Errors are short codes with no paths or stack traces; no debug mode; no cookies |
| 12 Logging | PASS | Logs go to stderr with field names only, never values. Alerts don't apply (gate 3) |
| 14 AI workflow | PASS, CI to do | Scanners, adversarial panel, Codex checks and hash-locked packages are done. The required CI check waits for the repo (MS-12) |
| 15 Periodic review | To do | Rerun after each new feature or snapshot |
| 16 Data rights | Not applicable | No accounts or personal data held for users. Public register figures are served only as rounded counts |

## Northern Ireland check
Rebuilt on the BT prefix, 5 to 6 Nov 2026 (`active/check_bt_switch.py`, not in the public repo, then every check below on the new data). The rebuild took about 23 minutes.

- **Rounding:** all pin checks found 0 pinned.
- **Old build against new:** UK totals are the same in all four tables, and 0 Great Britain council rows changed. Served rows that differ are only the unmatched area and the Great Britain totals that include it. The UK rows are the same.
- **Companies moved from Great Britain's unmatched group to Northern Ireland:** 872 live, 352 live from before 2021, 6,692 closed and 6,739 in the closures table. A dissolved company can sit in both of the last two, so these don't add up to a count of companies. No distinct count was made.
- **Lookup:** 60,399 rows have a Northern Ireland code and all of them start BT. 2,894 BT rows have no Northern Ireland code, and every BT postcode has a digit after BT.
- **Tests:** `test_northern_ireland_comes_from_the_postcode` failed before the rebuild and passes after.

Exact-count checks on the new data, all exit 0:

| Check | Result |
|---|---|
| `check_breakdown` | 68 verdicts, 5,415 Great Britain verdicts and 27 total verdicts, 0 wrong |
| `check_two_areas` | 9,640 pairs: 2,627 "more" and 11 "faster", 0 wrong |
| `check_levels` | 12,549 ranges, 0 outside; 108 clear share verdicts, 0 the wrong way |
| `check_largest` | 11,476 rows, 0 outside range or rank; 853 single ranks, 0 wrong |
| `check_regions` | 0 of 1,650 answers, 0 of 5,377 quarter rows and 0 of 412 survival ranges outside; 1 of 7,633 one-council rows outside, the same as before the rebuild |
| `check_closures` | 1,379 clear verdicts, 0 the wrong way, 134 held back by the address guard, 3 of 11,130 figures outside their range |
| `check_rank_basis` | 39 of 39 named areas hold; 0 clearly the other way |
| `check_standouts` | Growth 25 of 25 hold; survival names none |
| `check_fewer_than_10` | 679 of 65,126 shown under 10 are really 10 or more (1.04%) |
| `check_query`, `hand_check`, `hand_check_area` | all pass or match |
| `sweep` | 12,181 answers, 0 problems; 30 expected refusals; slowest 0.45 s |

Each `memo_numbers` figure that `MEMO.md` quotes still matches. The closures check moved by one verdict from the 1,378 and 135 recorded in `DECISIONS.md`; the other summary figures recorded there still match.

## Build and date
Audited at 17894ac plus the fixes above, 5 Nov 2026, on the Mac that built it. Rebuilt on the BT prefix and every check rerun on 5 to 6 Nov 2026.

## Results
- **Pillar 1:** no paid or external call is reachable from a tool. The server makes no network calls, DuckDB external access is off, and it writes no files. Companies House scripts have timeouts and capped retries: 6 attempts per request, and 3 per day in the closures download.
- **Pillar 2:** ready in 0.63 s; slowest of 17 measured calls 0.33 s; slowest of the 12,181 sweep answers 0.45 s. SIC input is capped at 20 items, lists at 25 rows, searches at 15 rows, and area rows at the number of areas.
- **Pillar 3:** not applicable (no user interface).
- **Failure drill:** the only dependency is a local file. Missing or unreadable files and files with any table missing now give `NO_DATA`, and the server recovers with no restart once the file is built. Damage deep inside a file that still opens gives `INTERNAL`; the export replaces the file whole, so a build can't leave it half-written. There is no remote service to stall.

## Codex checks
Six fresh read-only sessions: two on the first findings (one tried to disprove them, one listed scope), then four on the fixes and this report. The first five gave PASS WITH FIXES, which led to the required-tables check, the test of all 12 tools, the corrected figures here and narrower README wording. The sixth, a narrow check of the final README, DECISIONS, this file and `db()`, gave PASS. Codex couldn't repeat the timings, sizes, memory figure or drill under its limits, so those remain my measurements.

A seventh fresh session checked d43e0cb, the Northern Ireland commit: PASS WITH FIXES. It found that the new-snapshot block checked a date typed into the script, so a new file at the same path would have passed. The block now checks the file's SHA-256, with a test that fails if the check is removed. Its other two notes were low: one wording fix, made, and identifying details left in `DECISIONS.md` about MCP A, B and C, which stay because the comparison depends on them (the exact line count is gone).

An eighth session checked 20a1421: PASS WITH FIXES. The README's refresh steps didn't mention the block, now fixed. Two notes were rejected after checking. `build_levels.py` and `export_serving.py` read only `grid.duckdb`, so they can't bring in a new snapshot. The wider pattern in `testing_results.py` picks the same rows as the old one from both fixed reports.

A ninth session checked 2a92e5a: PASS WITH FIXES. The block covers the snapshot file only, not the closed-company downloads, so "blocked" overstated it; the README and SC-12 now say so. Pinning those downloads was left out, as a fresh download can differ and would stop a stranger's build. It also noted that it can't verify the `testing_results.py` comparison, because reviewers may not read those reports. That comparison was run by the builder, and the script's output stays private.

A tenth session checked that wording at 0d8d802: PASS. An eleventh session reviewed ec72925, the last changes before publishing: PASS WITH FIXES. The README said a failed build deletes its output, but a failure in the later `build_levels.py` checks leaves the raw grid behind, so the sentence was corrected. It also flagged `active/coverage/coverage.csv` in the first simulated tree note; that stays, because README step 3 creates that file. Twelfth and thirteenth sessions checked those corrections: PASS WITH FIXES on the audit wording, then PASS at ef8b37d.

## Not tested
- A data file that opens but is damaged inside or has different columns: it isn't caught as `NO_DATA`, and the README says so.
- Long-running server under sustained load (CA-5).
- A real public clone built from scratch: the simulation reused the existing `data/`.
- Linux: only macOS was run.
- Clients other than Claude Code and Claude Desktop.
