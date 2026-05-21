"""Source-marker regression tests (CROSS_PROJECT_LESSONS.md section 2).

Each SMOKE fix leaves a marker in the source it guards; this asserts the marker
is still present, so a later refactor that drops the guard fails CI.
"""
import inspect

from seljuk import actions


def test_smoke_001_marker_present():
    """SMOKE-001: Strategic Objective 'place' enumerates concrete targets."""
    assert "SMOKE-001" in inspect.getsource(actions)
