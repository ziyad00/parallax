"""Core data model and grouping logic.

The shape is intentionally generic — language-agnostic, unit-agnostic,
resource-agnostic. A Unit is any addressable piece of code (a function,
method, class, file, module, container, or whole microservice). A
Resource is any opaque identifier the unit touches (a database table,
an HTTP endpoint, a file path, an env var, a Kafka topic, a config key,
etc.).

Two units are considered candidates for consolidation when they touch
the same resource set, regardless of language, framework, or how the
underlying code is written.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Unit:
    """An addressable piece of code that touches some resources.

    The granularity is up to the extractor. Examples:

    - A Python function or method (extractor: python-sqlalchemy)
    - A whole TypeScript module (extractor: ts-axios-calls)
    - A Terraform resource block (extractor: terraform-aws)
    - A whole microservice (extractor: docker-compose-services)
    - A SQL view or stored procedure (extractor: postgres-views)

    ``location`` is the human-readable address — typically
    ``relative/path:line`` — used when reporting clusters.

    ``resources`` is a frozen set of opaque identifiers. Two units
    sharing this set are grouped together.
    """

    location: str  # e.g. "src/api/users.py:42"
    name: str  # e.g. "UserService.find_active"
    resources: frozenset[str]
    language: str = ""  # "python", "typescript", "go", "terraform", ...
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Cluster:
    """A group of units sharing the same resource set."""

    resources: frozenset[str]
    units: list[Unit]

    @property
    def size(self) -> int:
        return len(self.units)


def group_by_resource_set(
    units: Iterable[Unit],
    *,
    min_resources: int = 1,
    min_cluster_size: int = 2,
) -> list[Cluster]:
    """Group units by their resource set; return non-trivial clusters.

    ``min_resources`` filters out clusters whose resource set is too
    small to be interesting (e.g. a single shared resource is often
    generic — ``users`` table touched by 200 functions in any web app).

    ``min_cluster_size`` filters single-unit "clusters" (not a
    duplication candidate).

    Result is sorted: largest clusters first, then by resource-set
    size descending so deeper overlaps surface first.
    """
    by_resources: dict[frozenset[str], list[Unit]] = defaultdict(list)
    for unit in units:
        by_resources[unit.resources].append(unit)

    clusters: list[Cluster] = []
    for resources, members in by_resources.items():
        if len(members) < min_cluster_size:
            continue
        if len(resources) < min_resources:
            continue
        clusters.append(Cluster(resources=resources, units=members))

    clusters.sort(key=lambda c: (-c.size, -len(c.resources)))
    return clusters
