# Market Pulse MCP (lesson build)

A portfolio MCP server that answers questions about UK companies by fine industry (SIC code), area and month, from the free Companies House snapshot and its closed-company records. Every stored count is randomly rounded to 5, every answer states its caveats, and a count below 10 shows as "under 10 (rounded)".

## How we work (James, 1 Nov 2026)
- **Lesson build.** James sets the direction and makes the decisions; Claude writes the code, including the first SQL count query, the thin-count refusal rule and the ONS gap calculation. Claude explains each concept first in plain English, scaffolds the boring parts, then reviews James's code. Each ticket ends with a short note in `lessons/NN-topic.md`.
- **A builder never reviews its own work.** Each ticket gets a fresh reviewer before it's done.

## Hard rules
- **Read-only.** The server never writes anywhere except its local database and the snapshot archive.
- **v1 scope:** new incorporations only, from the live snapshot. Hard cap of 25 hours (log hours in `DECISIONS.md`). Phase B (1 Nov) added dissolved companies through the free API, for the backfill only; the server itself makes no network calls.
- **Serving:** the server opens only `data/serve.duckdb` (protected tables). `data/grid.duckdb` holds raw counts for checks and tests, and is never served or shared.
- **Every answer** carries its count, the snapshot date, and the survivorship caveat (closed companies are missing, so older periods under-count).
- **Public commits** credit jamesy456 alone, with no co-author line (James, 6 Nov 2026).
- **Data files stay out of git** (`data/` is ignored). The served snapshot is in `data/snapshots/`; a new one is blocked until the two-snapshot check exists (SC-12 in `AUDIT-FINDINGS.md`).
- **Downloads:** the snapshot comes only from download.companieshouse.gov.uk (robots.txt allows it). Ask James before each download.

## Handover rules (from day one)
- **Secrets** live only in `.env` (gitignored). `.env.example` lists the names.
- **Error logging:** no silent catches; log in plain English.
- **Failure alerts:** nothing runs on a schedule yet, so there's no alert; a failed build stops with an error.
- **Rate limits:** none in v1 (no API). If the API is added later: 600 requests per 5 minutes, back off on 429.
- **README:** a non-technical README.

## Checkpoints
- **Week 1:** the user is named, and one real question is answered by hand from the CSV before any MCP code.
- **Hour 12 (kill check):** coverage (snapshot ÷ Companies House official incorporations) for the latest complete quarter is 90–102%, and no quarter is above 102%. Fail → one fix attempt (max 2 h), then stop and switch to the Xero build. (Replaced the ONS 30% line on 1 Nov; see DECISIONS.md.)
- **Week 3:** the user asks three real questions and says whether they'd use it again.
- **Hour 25:** done, or stop.

## Gotchas
- **Any change to tool output wording, field descriptions or server instructions means rerunning `scripts/e2e.py` before the phase is done** (it costs about $1). Phase B changed the summary wording and nobody reran it until Phase D, which found word-for-word quoting down from 15/15 (v1) to 6/15, and harness patterns that no longer matched the new wording. `e2e.py rescore` re-checks saved answers for free.
- **Tool functions called directly in Python** (scripts, not MCP) get pydantic `Field` objects as defaults, and a `Field` is truthy. Pass every argument in direct calls; adding a flag to a tool means updating `scripts/memo_numbers.py` (a test checks it still reproduces MEMO.md).
