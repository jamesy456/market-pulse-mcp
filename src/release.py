"""The one exit for every number (SPEC: release(n) and the change test)."""
from math import log, sqrt
from statistics import NormalDist

MIN_SHOWN = 10  # below this, no count and no comparison
LOW = 30  # below this, or if the likely range reaches 0, the count is shown but flagged "low"
ROUND_TO = 5  # every published count is rounded, so subtracting two answers can't isolate a small one
# v5 review: a threshold on rounded sums can still be misled by rounding, so a "clear" verdict says so.
TEST_NOTE = " (a test that allows for rounding, not certain)"
# Case C7: "fewer than 10" was shown for a true 13. Summed cells can each be up to 4 below the truth, so the label
# says only what the rounded count is, and SMALL_NOTE says the true count may be higher.
SMALL = "under 10 (rounded)"
SMALL_NOTE = (" 'Under 10 (rounded)' means the rounded count is below 10, so no number is shown; the true count "
              "may be somewhat higher.")
CELL_VAR = 6.25  # most variance random rounding to 5 adds per protected cell: r(5 - r) <= 2.5 * 2.5


def _round(x: float) -> int:
    return ROUND_TO * round(x / ROUND_TO)


def release(n: int, cells: int = 1) -> dict:
    """Turn a raw count into what the client may see.

    Below 10: SMALL, no number. Otherwise the count rounded to the nearest 5, plus a
    likely range of +/- 2*sqrt (roughly 95% if counts behave like Poisson noise), also rounded.
    Everything after the < 10 check uses only the rounded count, so the output reveals nothing finer.
    `cells` is how many protected cells were summed (from the question's shape, never the data); their
    rounding noise widens the range.
    """
    if n < MIN_SHOWN:
        return {"count": None, "display": SMALL, "range": None, "low": True}
    shown = _round(n)
    spread = 2 * sqrt(shown + CELL_VAR * cells)
    return {"count": shown, "display": f"{shown:,}",
            "range": [max(0, _round(shown - spread)), _round(shown + spread)], "low": shown < LOW or spread >= shown}


def change(a: int, b: int, cells_a: int = 0, cells_b: int = 0, tests: int = 1) -> str:
    """Compare an earlier count a with a later count b (protected sums, server side).

    A change is clear only if both are >= 10 and |a - b| > 2 * sqrt(a + b + rounding variance of both), with the
    2 raised (Bonferroni) when `tests` changes are tested at once.
    """
    if a < MIN_SHOWN or b < MIN_SHOWN:
        return "too few to compare"
    if abs(b - a) <= z_needed(tests) * sqrt(a + b + CELL_VAR * (cells_a + cells_b)):
        return "no clear change"
    return f"clear {'increase' if b > a else 'decrease'} in this snapshot{TEST_NOTE}"


def share_z(a1: int, n1: int, a2: int, n2: int, cells_a: int | tuple = 0, cells_n: int | tuple = 0,
            shift: bool = False) -> float:
    """Did count a's share of total n change between two periods? Log odds ratio of a against the rest of n.

    Poisson variance plus up to CELL_VAR per protected cell summed. cells_n is the rest of n's cells; either may be
    a pair (earlier, later) when the periods differ (batch B: a total shown at 50 or more is one cell). With cells
    this is the cautious z (the most rounding could add); with cells=0 it is the bold z (no rounding allowed for).
    """
    (a_1, a_2), (n_1, n_2) = (c if isinstance(c, tuple) else (c, c) for c in (cells_a, cells_n))
    return odds_z(a1, n1 - a1, a2, n2 - a2, (a_1, n_1, a_2, n_2), shift)


def odds_z(a1: int, b1: int, a2: int, b2: int, cells: tuple = (0, 0, 0, 0), shift: bool = False) -> float:
    """Log odds ratio z of (a2 against b2) versus (a1 against b1). `cells` gives each count's protected cells, so
    counts summed from different numbers of cells (an area and the rest of GB) each get their own rounding variance."""
    # Batch B, for lists that pick standouts from hundreds of areas (shift=True): picking the strongest favours areas
    # whose rounding pushed them over the bar, and the variance allowance alone let one through that the exact counts
    # didn't support (scripts/check_standouts.py, Westminster 68: exact z 3.78 against 3.80). So each count is first
    # moved toward no change by what its rounding plausibly moved it: 4 per cell, at most 1 sd of the noise. Single
    # answers don't select, had 0 wrong without it, and lose most verdicts with it (compare 108 -> 51, faster 11 -> 0).
    if shift:
        up = log(a2 / b2) > log(a1 / b1)
        moves = [min(4 * c, sqrt(CELL_VAR * c)) for c in cells]
        a1, b1, a2, b2 = (x + (m if grow else -m) for x, m, grow in zip((a1, b1, a2, b2), moves, (up, not up, not up, up)))
        if min(a1, b1, a2, b2) <= 0 or (log(a2 / b2) > log(a1 / b1)) != up:
            return 0.0
    var = sum((x + CELL_VAR * c) / x**2 for x, c in zip((a1, b1, a2, b2), cells))
    return (log(a2 / b2) - log(a1 / b1)) / sqrt(var)


def rate_range(c: int, s: int, cells_c: int, cells_s: int) -> tuple[float, float]:
    """Likely range (+/- 2 sd) of the rate s / (c + s), from protected sums: Poisson variance plus up to CELL_VAR
    per protected cell in each part (delta method). Phase C: small numerators made exact-looking rates wrong."""
    n = c + s
    var = (s * s * (c + CELL_VAR * cells_c) + c * c * (s + CELL_VAR * cells_s)) / n**4
    p, sd = s / n, sqrt(var)
    return max(0.0, p - 2 * sd), min(1.0, p + 2 * sd)


def z_needed(tests: int = 1) -> float:
    """Two-sided 95% threshold, Bonferroni-corrected when many areas are tested at once (2.0 for one test)."""
    return 2.0 if tests <= 1 else NormalDist().inv_cdf(1 - 0.025 / tests)


def share_change(a1: int, n1: int, a2: int, n2: int, cells_a: int | tuple, cells_n: int | tuple,
                 tests: int = 1) -> str:
    """Verdict on a share change, from protected sums (server side). Only the z that allows for rounding counts:
    the Phase C benchmark showed a tier that ignored rounding labelled rounding artefacts."""
    if min(a1, a2, n1 - a1, n2 - a2) < MIN_SHOWN:
        return "too few to compare"
    need = z_needed(tests)
    z = share_z(a1, n1, a2, n2, cells_a, cells_n, tests > 1)  # many tests at once: a list picking standouts
    return f"clear {'rise' if z > 0 else 'fall'} in share in this snapshot{TEST_NOTE}" if abs(z) > need else "no clear change in share"
