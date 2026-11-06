# AUDIT-PROFILE
type: mcp-server
stack: Python 3.12, DuckDB 2.0.0 (read-only file), MCP SDK 2.3.0 over stdio; runs on the user's own machine
metered: none at query time. Developer-only scripts spend money or quota when run by hand: e2e.py and benchmark*.py (AI runs), backfill_*.py and closed_check.py (free Companies House API)
auth: none (local stdio; the client starts the process)   payments: none
user data: none. Tool inputs are industry codes, area codes, quarters and short search text; nothing is stored
profiles loaded: none (mcp-server row: `mcp-security`, then the usual stages)
not applicable: Pillar 3 and Pass A viewports (no user interface; agent-facing wording was reviewed in the 5 Nov final review), payment lifecycle (no payments), scheduled jobs and overlap (none exist), alerting and outside monitoring (handover rule 3, not applicable: no scheduled job, and errors go straight back to the person asking)
