from release import TEST_NOTE, change, release


def test_release_boundaries():
    assert release(9) == {"count": None, "display": "under 10 (rounded)", "range": None, "low": True}
    assert release(10)["count"] == 10 and release(10)["low"]
    assert release(27)["low"] and not release(28)["low"]  # "low" means a published count below 30
    assert release(100)["range"] == [80, 120]


def test_release_rounds_to_5():
    assert [release(n)["count"] for n in (12, 13, 19, 20, 1048)] == [10, 15, 20, 20, 1050]
    assert all(x % 5 == 0 for n in range(10, 2000) for x in [release(n)["count"], *release(n)["range"]])


def test_output_depends_only_on_the_rounded_count():
    # Review 2, B1: a (count, range) pair must never narrow n below its rounding bucket.
    seen = {}
    for n in range(10, 5000):
        r = release(n)
        assert seen.setdefault(r["count"], r) == r


def test_change():
    assert change(30, 20) == "no clear change"
    assert change(60, 120) == "clear increase in this snapshot" + TEST_NOTE
    assert change(120, 60) == "clear decrease in this snapshot" + TEST_NOTE
    assert change(9, 200) == "too few to compare"


def test_phase_a_share_change():
    from release import share_change, z_needed
    assert share_change(5, 1000, 50, 1000, 0, 0) == "too few to compare"
    assert share_change(100, 10000, 300, 10000, 0, 0) == "clear rise in share in this snapshot" + TEST_NOTE
    assert share_change(300, 10000, 100, 10000, 0, 0) == "clear fall in share in this snapshot" + TEST_NOTE
    assert share_change(100, 10000, 105, 10000, 0, 0) == "no clear change in share"
    # clears the bar only if rounding added nothing: not counted (Phase C)
    assert share_change(100, 10000, 135, 10000, 40, 0) == "no clear change in share"
    assert z_needed(1) == 2.0 and z_needed(300) > 3.5


def test_odds_z_is_share_z_with_per_count_cells():
    from release import odds_z, share_z
    assert odds_z(30, 970, 60, 940, (4, 9, 4, 9)) == share_z(30, 1000, 60, 1000, 4, 9)


def test_batch_b_cautious_z_moves_counts_toward_no_change():
    from release import odds_z
    assert odds_z(100, 900, 102, 898) > 0 and odds_z(100, 900, 102, 898, (1, 1, 1, 1)) > 0  # single answers: no shift
    assert odds_z(100, 900, 102, 898, (1, 1, 1, 1), True) == 0.0  # within one cell's rounding of no change
    assert 0 < odds_z(100, 900, 160, 840, (1, 1, 1, 1), True) < odds_z(100, 900, 160, 840)
    assert 0 > odds_z(160, 840, 100, 900, (1, 1, 1, 1), True) > odds_z(160, 840, 100, 900)
