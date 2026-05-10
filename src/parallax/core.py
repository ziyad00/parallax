"""Core data model and grouping engine.

A :class:`Unit` is any addressable piece of code that touches a set
of resources (database tables, HTTP endpoints, Redis keys, env vars,
...). Units sharing the same resource set are grouped into a
:class:`Cluster` and ranked by an interestingness score.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Union


@dataclass(frozen=True)
class Unit:
    """An addressable piece of code that touches some resources.

    The granularity is up to the extractor (function, file, module).
    ``location`` is the human-readable address (typically
    ``relative/path:line``); ``resources`` is the frozen set of
    opaque identifiers the unit touches.
    """

    location: str
    name: str
    resources: frozenset[str]
    language: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Cluster:
    """A group of units sharing the same resource set."""

    resources: frozenset[str]
    units: list[Unit]
    score: float = 0.0  # Filled in by ``group_by_resource_set``.
    name_similarity: float = 0.0  # 0..1 ; mean pairwise unit-name similarity.

    @property
    def size(self) -> int:
        return len(self.units)

    @property
    def files(self) -> set[str]:
        """Distinct file paths the cluster spans (everything before any ':')."""
        return {u.location.split(":", 1)[0] for u in self.units}

    @property
    def is_cross_file(self) -> bool:
        """True if this cluster spans more than one file."""
        return len(self.files) > 1


@dataclass(frozen=True)
class FoldedGroup:
    """A class+file grouping that folds N member methods into one report row.

    Produced by :func:`fold_units_by_class` when a class contributes
    many methods to a single cluster. The full member list is kept in
    ``method_names`` so reporters can offer a drill-down.
    """

    file: str
    class_name: str
    method_count: int
    method_names: list[str]
    location: str  # ``file:lineno`` of the first method, for clickable hop-to.
    language: str = ""


def _resource_frequencies(units: Iterable[Unit]) -> dict[str, float]:
    """Per-resource frequency: fraction of units that reference it."""
    units = list(units)
    if not units:
        return {}
    total = len(units)
    counts: Counter[str] = Counter()
    for u in units:
        for r in u.resources:
            counts[r] += 1
    return {r: c / total for r, c in counts.items()}


def _name_similarity(units: list[Unit]) -> float:
    """Mean pairwise similarity of unit names (0..1).

    Names are stripped of class qualifiers first so a cluster of
    repository methods compares on the method names, not the
    (identical) class prefix.
    """
    if len(units) < 2:
        return 0.0
    short = [u.name.rsplit(".", 1)[-1] for u in units]
    total = 0.0
    pairs = 0
    for i in range(len(short)):
        for j in range(i + 1, len(short)):
            total += SequenceMatcher(None, short[i], short[j]).ratio()
            pairs += 1
    return total / pairs if pairs else 0.0


def _cluster_score(
    cluster: Cluster,
    *,
    freqs: dict[str, float],
    cross_file_weight: float = 1.5,
    same_file_weight: float = 0.4,
    name_similarity_boost: float = 0.5,
) -> float:
    """Interestingness score for a cluster.

    Combines size, resource-set breadth, average resource rarity
    (rarer co-occurrence = more interesting), a cross-file factor,
    and an optional name-similarity bonus.
    """
    if not cluster.resources:
        return 0.0
    rarity = sum(1.0 - freqs.get(r, 0.0) for r in cluster.resources) / len(
        cluster.resources
    )
    breadth = len(cluster.resources)
    file_factor = cross_file_weight if cluster.is_cross_file else same_file_weight
    # Squaring rarity makes hub tables (User, Place) penalise the
    # cluster non-linearly. Without this, raw size compensates for
    # universal tables and noisy clusters tie with specific ones.
    base = (rarity ** 2) * cluster.size * breadth * file_factor
    similarity_factor = 1.0 + cluster.name_similarity * name_similarity_boost
    return base * similarity_factor


def group_by_resource_set(
    units: Iterable[Unit],
    *,
    min_resources: int = 1,
    min_cluster_size: int = 2,
    cross_file_only: bool = False,
) -> list[Cluster]:
    """Group units by their resource set and return scored clusters.

    ``min_resources`` filters clusters with too-small resource sets.
    ``min_cluster_size`` filters singletons. ``cross_file_only``
    drops clusters whose units all live in one file (typically a
    cohesive class, not architectural duplication).
    """
    units = list(units)
    by_resources: dict[frozenset[str], list[Unit]] = defaultdict(list)
    for unit in units:
        by_resources[unit.resources].append(unit)

    freqs = _resource_frequencies(units)

    clusters: list[Cluster] = []
    for resources, members in by_resources.items():
        if len(members) < min_cluster_size:
            continue
        if len(resources) < min_resources:
            continue
        cluster = Cluster(resources=resources, units=members)
        if cross_file_only and not cluster.is_cross_file:
            continue
        cluster.name_similarity = _name_similarity(members)
        cluster.score = _cluster_score(cluster, freqs=freqs)
        clusters.append(cluster)

    clusters.sort(key=lambda c: (-c.score, -c.size, -len(c.resources)))
    return clusters


def fold_units_by_class(
    units: list[Unit],
    *,
    threshold: int = 5,
) -> list[Union[Unit, FoldedGroup]]:
    """Collapse N+ methods of the same class into a single FoldedGroup row.

    Methods below the threshold pass through unchanged. The original
    ``Cluster.units`` list is not mutated.
    """
    if threshold < 2:
        return list(units)

    by_group: dict[tuple[str, str], list[Unit]] = defaultdict(list)
    order: list[tuple[str, str]] = []
    for u in units:
        key = _class_file_key(u)
        if key not in by_group:
            order.append(key)
        by_group[key].append(u)

    out: list[Union[Unit, FoldedGroup]] = []
    for key in order:
        members = by_group[key]
        file_path, class_name = key
        if class_name and len(members) >= threshold:
            method_names = [m.name.rsplit(".", 1)[-1] for m in members]
            out.append(
                FoldedGroup(
                    file=file_path,
                    class_name=class_name,
                    method_count=len(members),
                    method_names=method_names,
                    location=members[0].location,
                    language=members[0].language,
                )
            )
        else:
            out.extend(members)
    return out


def _class_file_key(unit: Unit) -> tuple[str, str]:
    """Return ``(file, class_name)``. ``class_name`` is empty for free functions."""
    file_part = unit.location.split(":", 1)[0]
    class_part = unit.name.rsplit(".", 1)[0] if "." in unit.name else ""
    return (file_part, class_part)
