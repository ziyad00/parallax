"""Smoke tests for the axis-coverage analysis."""

from __future__ import annotations

from parallax import Unit, axis_coverage, render_axis_report


def _u(loc: str, *resources: str, name: str = "") -> Unit:
    return Unit(
        location=loc,
        name=name or loc.rsplit("/", 1)[-1],
        resources=frozenset(resources),
        language="python",
    )


def test_groups_units_by_subset_of_axis():
    units = [
        _u("dm_service.py", "DMThread", "User"),
        _u("group_service.py", "GroupChat", "User"),
        _u("place_chat_service.py", "PlaceChatMessage", "User"),
        # The "this file handles dm+group but forgot place" case.
        _u("inbox_service.py", "DMThread", "GroupChat", "User"),
        # The unrelated case — touches none of the axis members.
        _u("auth_service.py", "User"),
    ]
    axis = ["DMThread", "GroupChat", "PlaceChatMessage"]

    groups = axis_coverage(units, axis)

    # auth_service has no axis touch → dropped.
    assert sum(g.size for g in groups) == 4

    by_touched = {tuple(sorted(g.touched)): g for g in groups}
    assert ("DMThread",) in by_touched
    assert ("GroupChat",) in by_touched
    assert ("PlaceChatMessage",) in by_touched
    assert ("DMThread", "GroupChat") in by_touched

    inbox_group = by_touched[("DMThread", "GroupChat")]
    assert {u.location for u in inbox_group.units} == {"inbox_service.py"}
    assert inbox_group.missing == frozenset({"PlaceChatMessage"})
    assert inbox_group.is_complete is False


def test_partial_coverage_sorts_before_complete():
    units = [
        # Full coverage (3-of-3).
        _u("full.py", "A", "B", "C"),
        # Partial (2-of-3) — should rank above the singleton.
        _u("two.py", "A", "B"),
        # Singletons.
        _u("only_a.py", "A"),
        _u("only_b.py", "B"),
    ]
    groups = axis_coverage(units, ["A", "B", "C"])

    # First group is the 2-of-3 (highest |touched| within partials).
    assert sorted(groups[0].touched) == ["A", "B"]
    assert groups[0].is_complete is False

    # Singleton partials follow.
    partial_ones = [g for g in groups if len(g.touched) == 1 and not g.is_complete]
    assert {tuple(sorted(g.touched)) for g in partial_ones} == {("A",), ("B",)}

    # Complete group last.
    assert groups[-1].is_complete is True


def test_empty_axis_returns_empty():
    assert axis_coverage([_u("x.py", "A")], []) == []


def test_render_axis_report_marks_complete():
    units = [
        _u("inbox.py", "DMThread", "GroupChat"),
        _u("all.py", "DMThread", "GroupChat", "PlaceChatMessage"),
    ]
    groups = axis_coverage(units, ["DMThread", "GroupChat", "PlaceChatMessage"])
    report = render_axis_report(
        groups,
        axis=["DMThread", "GroupChat", "PlaceChatMessage"],
        scanned_units=2,
    )
    # Partial-coverage block appears, with the missing member named.
    assert "missing: [PlaceChatMessage]" in report
    # Complete-coverage block is marked clearly so readers don't squint.
    assert "complete" in report
    # Both files surface in the output.
    assert "inbox.py" in report
    assert "all.py" in report
