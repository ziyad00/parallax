"""JSON output."""

from __future__ import annotations

import json
from typing import Iterable

from ..core import Cluster


def render_json(
    clusters: Iterable[Cluster],
    *,
    scanned_units: int,
) -> str:
    clusters = list(clusters)
    payload = {
        "scanned": scanned_units,
        "clusters": [
            {
                "resources": sorted(c.resources),
                "size": c.size,
                "score": round(c.score, 4),
                "name_similarity": round(c.name_similarity, 4),
                "is_cross_file": c.is_cross_file,
                "units": [
                    {
                        "location": u.location,
                        "name": u.name,
                        "language": u.language,
                        "resources": sorted(u.resources),
                    }
                    for u in c.units
                ],
            }
            for c in clusters
        ],
    }
    return json.dumps(payload, indent=2)
