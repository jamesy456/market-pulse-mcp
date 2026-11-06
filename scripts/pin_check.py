"""Build-time check (review 5, F1): can the published protected tables pin any raw count below 10?

Each protected value p means the raw count is in [max(0, p-4), p+4]. Per (sic, year, quarter):
  sum(p_area cells) + sum(p_mass cells) + NI (unpublished, >= 0) = UK total, which p_uk bounds.
Interval propagation over that sum finds the bounds a client could derive by combining answers. The build fails
if any cell that could be below 10 is pinned to one value. Narrower-but-not-exact intervals are counted and logged
(UK cells included; the NI remainder always spans 9+ values, so it is never pinned). This is the accepted
residual of independently rounded overlapping tables, as with ONS cell-key tables.
"""
from collections import defaultdict

INF = float("inf")


def bounds(p: int) -> list[float]:
    return [max(0, p - 4), p + 4]


def narrowed(groups: dict) -> list:
    """groups: key -> (uk p, [area and mass cell p]). Returns (key, p, derived interval) for every narrowed small cell."""
    out = []
    for key, (uk, cells) in groups.items():
        lo_sum = sum(bounds(p)[0] for p in cells)
        uk_hi = uk + 4  # NI >= 0 and has no upper bound, so only the upper bound of each cell can move
        for p in cells:
            lo, hi = bounds(p)
            new_hi = min(hi, uk_hi - (lo_sum - lo))
            if lo < 10 and new_hi < hi:
                out.append((key, p, [lo, new_hi]))
        lo, hi = bounds(uk)  # review 6: the UK raw cell itself is at least the sum of its parts' lower bounds
        if lo < 10 and lo_sum > lo:
            out.append(((key, "uk"), uk, [lo_sum, hi]))
    return out


def check(con, suffix: str = "", extra: str = "") -> tuple[list, list]:
    """Returns (pinned, narrowed) for a built grid connection. suffix/extra pick a table family and its extra
    key columns (phase B: "_closed", ", age"), which keep the same area + mass + NI = UK structure."""
    groups = defaultdict(lambda: [0, []])
    for *k, v in con.execute(f"SELECT sic, year, quarter{extra}, protected FROM p_uk{suffix}").fetchall():
        groups[tuple(k)][0] = v
    for t in ("p_area", "p_mass"):
        for *k, v in con.execute(f"SELECT sic, year, quarter{extra}, protected FROM {t}{suffix}").fetchall():
            groups[tuple(k)][1].append(v)
    leaks = narrowed(groups)
    return [x for x in leaks if x[2][1] <= x[2][0]], leaks


if __name__ == "__main__":
    # Review 5's scenario: UK shows 0, four cells show 5 each -> each pinned to exactly 1.
    assert sorted(b for *_, b in narrowed({"x": (0, [5, 5, 5, 5])})) == [[1, 1]] * 4 + [[4, 4]]  # cells 1 each, UK 4
    # A loose UK total teaches nothing.
    assert not narrowed({"y": (100, [30, 30, 40])})
    print("pin_check self-test ok")
