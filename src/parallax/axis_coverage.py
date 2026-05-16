"""Axis-coverage analysis.

Given a set of related resources — an *axis* — bucket every Unit by
which subset of the axis it touches. The intent is to surface the
"parallel-path coverage" bug family, where a feature has N analogous
code paths (DM / Group / Place chat; or follow / unfollow / cancel)
and one of them got forgotten in a cross-cutting change.

Example::

    parallax axis circles-be -e sqlalchemy \\
        --axis DMThread,GroupChat,PlaceChatMessage

prints, per coverage subset:

- ``inbox_service.py`` touches DMThread, GroupChat (missing PlaceChatMessage)
- ``unread_service.py`` touches DMThread (missing GroupChat, PlaceChatMessage)

The cross-cutting files showing partial coverage are the candidates
for "you forgot to do X for groups too" bugs. Specialized files
touching exactly one axis member are usually fine (a DM-only service
is allowed to be DM-only), but the report shows them anyway so the
asymmetry is visible at a glance.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .core import Unit


@dataclass(frozen=True)
class AxisGroup:
    """All units that touch the same subset of an axis.

    ``touched`` is the subset of axis members each member references;
    ``missing`` is the complement. A group is "complete" when ``missing``
    is empty.
    """

    touched: frozenset[str]
    missing: frozenset[str]
    units: list[Unit]

    @property
    def size(self) -> int:
        return len(self.units)

    @property
    def is_complete(self) -> bool:
        return not self.missing

    @property
    def files(self) -> set[str]:
        """Distinct file paths the group spans (everything before any ``:``)."""
        return {u.location.split(":", 1)[0] for u in self.units}


def axis_coverage(
    units: Iterable[Unit],
    axis: Iterable[str],
) -> list[AxisGroup]:
    """Bucket ``units`` by which subset of ``axis`` they touch.

    Units that touch zero axis members are dropped — they're outside
    the question being asked. The returned list is sorted so the most
    interesting groups appear first: partial coverage before complete
    coverage, then larger groups before smaller ones.

    Within partial-coverage groups, those touching MORE axis members
    rank higher — a file touching 2 of 3 axis members is more
    suspicious than one touching only 1, because the asymmetry is more
    "you almost handled all paths but missed one".
    """
    axis_set = frozenset(axis)
    if not axis_set:
        return []

    by_subset: dict[frozenset[str], list[Unit]] = defaultdict(list)
    for unit in units:
        touched = unit.resources & axis_set
        if not touched:
            continue
        by_subset[touched].append(unit)

    groups: list[AxisGroup] = []
    for touched, members in by_subset.items():
        groups.append(
            AxisGroup(
                touched=touched,
                missing=axis_set - touched,
                units=members,
            )
        )

    def sort_key(g: AxisGroup) -> tuple:
        # Most-suspicious first: partial coverage, more touched within
        # partials (the "2 of 3" case), then complete groups.
        return (
            g.is_complete,           # False < True → partial first
            -len(g.touched),         # More touched first within partials
            -g.size,                 # Larger groups first within ties
            sorted(g.touched),       # Deterministic tiebreak
        )

    groups.sort(key=sort_key)
    return groups


def render_axis_report(
    groups: list[AxisGroup],
    *,
    axis: Iterable[str],
    scanned_units: int,
) -> str:
    """Plain-text report. One section per coverage subset.

    Files in partial-coverage sections are the candidates a reviewer
    should check for "did you forget to handle the missing axis member
    in this file too?"
    """
    axis_list = sorted(axis)
    lines: list[str] = []
    lines.append(
        f"Scanned {scanned_units} units. "
        f"Axis: {', '.join(axis_list)}. "
        f"{sum(1 for g in groups if not g.is_complete)} partial-coverage group(s)."
    )
    lines.append("")

    if not groups:
        lines.append("No units touched any axis member.")
        return "\n".join(lines) + "\n"

    for group in groups:
        touched = sorted(group.touched)
        missing = sorted(group.missing)
        header = (
            f"touched: [{', '.join(touched)}]"
            + (f"  missing: [{', '.join(missing)}]" if missing else "  ✓ complete")
        )
        lines.append(f"--- {header}  ({group.size} unit(s)) ---")
        for unit in sorted(group.units, key=lambda u: (u.location, u.name)):
            short = unit.name.rsplit(".", 1)[-1] if "." in unit.name else unit.name
            lines.append(f"    [{unit.language or 'text'}] {unit.location}::{short}")
        lines.append("")

    return "\n".join(lines)
