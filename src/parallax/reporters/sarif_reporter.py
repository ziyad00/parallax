"""SARIF v2.1.0 reporter.

Each cluster becomes a SARIF result with rule ``PARA001``. Suitable
for upload via ``actions/upload-sarif``.
"""

from __future__ import annotations

import json
from typing import Iterable

from ..core import Cluster
from .. import __version__


SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cs01/schemas/sarif-schema-2.1.0.json"
)


def render_sarif(
    clusters: Iterable[Cluster],
    *,
    scanned_units: int,
    extractors: list[str],
) -> str:
    clusters = list(clusters)

    rules = [
        {
            "id": "PARA001",
            "name": "ArchitecturalDuplication",
            "shortDescription": {"text": "Multiple units touch the same resource set"},
            "fullDescription": {
                "text": (
                    "Two or more units reference the same set of resources "
                    "and are likely candidates for consolidation."
                )
            },
            "defaultConfiguration": {"level": "note"},
            "helpUri": "https://github.com/ziyad00/parallax",
        }
    ]

    results: list[dict] = []
    for cluster in clusters:
        resources_label = ", ".join(sorted(cluster.resources))
        message = (
            f"{cluster.size} units share the resource set "
            f"[{resources_label}]."
        )
        primary = cluster.units[0]
        related = [_location_for_unit(u) for u in cluster.units[1:]]
        result = {
            "ruleId": "PARA001",
            "kind": "review",
            "level": "note",
            "message": {"text": message},
            "locations": [_location_for_unit(primary)],
            "relatedLocations": related,
            "properties": {
                "resources": sorted(cluster.resources),
                "clusterSize": cluster.size,
                "score": round(cluster.score, 4),
                "isCrossFile": cluster.is_cross_file,
            },
        }
        results.append(result)

    sarif = {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "parallax",
                        "version": __version__,
                        "informationUri": "https://github.com/ziyad00/parallax",
                        "rules": rules,
                    }
                },
                "results": results,
                "properties": {
                    "scannedUnits": scanned_units,
                    "extractors": extractors,
                },
            }
        ],
    }
    return json.dumps(sarif, indent=2)


def _location_for_unit(unit) -> dict:
    raw = unit.location
    file = raw
    line = 1
    if ":" in raw:
        file, _, lineno = raw.rpartition(":")
        try:
            line = int(lineno)
        except ValueError:
            file = raw
            line = 1
    return {
        "physicalLocation": {
            "artifactLocation": {"uri": file},
            "region": {"startLine": line},
        },
        "message": {"text": unit.name},
    }
