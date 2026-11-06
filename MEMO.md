# Are new digital companies forming faster in Leeds than in the rest of Great Britain?

> **PROXY QUESTION, NOT A REAL USER.** No council officer has replied yet, so this question comes from a published source. Leeds City Council's Economic Vision ([announced 24 October 2025](https://news.leeds.gov.uk/news/multibillion-economic-vision-for-leeds-to-drive-creation-of-100-000-jobs)) names Digital & Tech as one of three key growth sectors. The decision it would feed: **should start-up support in Leeds favour digital and tech founders?** This memo is redone if a real officer asks.

## Answer
**There's no sign Leeds is pulling ahead.** About 535 digital companies registered in Leeds in the last year were still open on 1 November 2026, against about 370 from the year before. Great Britain grew by a similar amount, so Leeds's share stayed at roughly 1.4%. The small difference is too small to be sure it's real.

| Companies still open on 1 Nov 2026 | Registered Q4 2024 – Q3 2025 | Registered Q4 2025 – Q3 2026 | Change |
|---|---|---|---|
| Leeds | about 370 (likely 325–415) | about 535 (likely 480–590) | +45% |
| Great Britain (council areas plus unmatched postcodes) | about 24,975 | about 38,120 | +53% |
| **Leeds's share** | **1.48%** | **1.40%** | **no clear change** |

Formation-agent addresses are left out of both rows (see the robustness check below). Figures updated 3 Nov 2026 for batch B, where Great Britain is its own rounded total rather than a sum of council areas (it was about 25,135 and 38,075, shares 1.47% and 1.41%); the conclusion is unchanged.

## Don't read the growth as real growth
These are companies that were **still open on 1 November 2026**. Companies that have since closed aren't counted, so the older year looks lower than it really was.
- **The data shows the gap.** Across all industries (companies, excluding LLPs), Companies House's official figures show registrations *fell* about 5% between these two years (818,153 to 775,576)¹. Yet the companies still open *rose* 21%, because the snapshot holds 76% of the older year's companies but 98% of the latest year's.
- **A large part of the +45% is closures.** If digital firms close at the all-industry rate, the real rise is about +13% for Leeds and +19% for Great Britain. Digital is still growing while companies overall fall, but Leeds isn't outpacing the rest.
- **The share is the fairer comparison.** It assumes digital firms close at roughly the same rate in Leeds as elsewhere. That is reasonable, but this data doesn't test it.

## Robustness check: with formation-agent addresses
Thousands of companies register at a formation agent's postcode, not where they work. Counting them changes the picture a little, but not the conclusion:

| Leeds's share of Great Britain | Older year | Latest year | Verdict |
|---|---|---|---|
| Agent addresses left out | 1.48% | 1.40% | no clear change |
| Agent addresses included | 1.03% | 0.89% | no clear change (a small fall that only clears the bar if rounding is ignored) |

The dip clears the 2-sigma rule only when rounding is ignored (z = −2.25; −1.70 allowing for it), so it isn't counted as real (after the Phase C benchmark, verdicts that ignore rounding were dropped). The dip comes from digital companies at agent addresses across Great Britain, which nearly doubled (about 14,705 to about 27,815). Leeds itself has very few (about 40 and 55). Either way, a flat share or a small fall, there is no sign Leeds is pulling ahead.

## What this can't tell you
- **Survival, jobs or size.** It doesn't say whether these firms will last, hire anyone or grow. The council's "over 3,000 digital and data companies" counts something different: firms of every age.
- **Where firms really work.** It uses the registered address only.
- **Industry is self-reported.** Each company picks its first SIC code itself. "Digital" here means seven codes: 62011, 62012, 62020, 62090, 63110, 63120 and 58290.
- **Coverage.** It counts private limited companies, PLCs and LLPs only, not sole traders.

## What I'd do with it
If the case for favouring digital founders is that digital start-ups are booming in Leeds, this data doesn't support that claim. New digital companies are growing at about the national rate. A stronger case would rest on survival or scale-up, which needs data this tool doesn't have.

---
*Source: Companies House Free Company Data Product, snapshot of 1 November 2026, via the Market Pulse MCP. All counts are rounded to 5 and protected. Every number here can be regenerated with `scripts/memo_numbers.py`. The method is in `DECISIONS.md`.*

*¹ Companies House changed its counting method from 2026-Q2, partway through the latest year. The two methods don't overlap in time, so the −5% compares figures across that change. Coverage is close to 100% under both.*
