"""Source-marker regression-test pattern (CROSS_PROJECT_LESSONS.md section 2).

Once SMOKE findings exist, each fix gets a one-liner here asserting its
``SMOKE-NNN`` marker is still present in the source it guards, so a later
refactor that drops the guard fails CI. Phase 0 has no findings yet; this file
documents the pattern and keeps the test module in place.
"""


def test_no_smoke_markers_expected_in_phase0():
    # Placeholder: SMOKE numbering begins in Phase 2+ (see SMOKE_TEST_FINDINGS.md).
    assert True
