"""Core data model + grouping/scoring engine.

A :class:`Unit` is any addressable piece of code (function, method,
file, microservice, ...) that touches a set of :class:`resources <str>`
(database tables, HTTP endpoints, Redis keys, env vars, ...). Two
units sharing the same resource set are doing the same logical job
and surface as a :class:`Cluster`.

Each cluster is scored by *interestingness* — a function of cluster
size, resource-set size, **resource rarity** (cluster discounting hub
tables like ``User`` that are touched everywhere), and whether the
cluster crosses file boundaries. The score sorts the report so the
most actionable findings rise to the top.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable


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


def _cluster_score(
    cluster: Cluster,
    *,
    freqs: dict[str, float],
    cross_file_weight: float = 1.5,
    same_file_weight: float = 0.4,
) -> float:
    """Interestingness score for a cluster.

    The score combines four signals:

    * **Size** — more co-occurring members is more suspicious.
    * **Resource breadth** — clusters touching more distinct resources
      are typically more meaningful (a 5-table cluster is rarer than
      a 2-table one).
    * **Rarity** — average ``1 - freq(t)`` across the cluster's
      resources. Hub tables (touched by 80%+ of units) drag the
      score down so generic ``[User, Place]``-style noise stops
      dominating the report.
    * **Cross-file factor** — clusters spanning multiple files are
      multiplied up; clusters confined to one file are discounted
      (likely a cohesive class, not duplication).

    All weights are tuned for 'sensible defaults out of the box'; no
    knobs are exposed in v0.2 to keep the CLI simple. Plug in custom
    scoring functions if needed.
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
    return (rarity ** 2) * cluster.size * breadth * file_factor


def group_by_resource_set(
    units: Iterable[Unit],
    *,
    min_resources: int = 1,
    min_cluster_size: int = 2,
    cross_file_only: bool = False,
) -> list[Cluster]:
    """Group units by their resource set, score, and return clusters.

    ``min_resources`` filters out clusters whose resource set is too
    small to be interesting. ``min_cluster_size`` filters singletons.
    ``cross_file_only`` (added in v0.2) drops clusters whose units all
    live in one file — those are usually cohesive class methods, not
    architectural duplication.

    Result is sorted by interestingness score, descending.
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
        cluster.score = _cluster_score(cluster, freqs=freqs)
        clusters.append(cluster)

    clusters.sort(key=lambda c: (-c.score, -c.size, -len(c.resources)))
    return clusters
