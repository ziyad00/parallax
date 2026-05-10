"""Plain-text reporter — what the CLI's default output looked like."""

from __future__ import annotations

from typing import Iterable

from ..core import Cluster


def render_text(
    clusters: Iterable[Cluster],
    *,
    scanned_units: int,
    extractors: list[str],
    min_resources: int,
    min_cluster_size: int,
) -> str:
    clusters = list(clusters)
    lines: list[str] = [
        f"Scanned {scanned_units} units (extractors: {', '.join(extractors)}). "
        f"Found {len(clusters)} clusters "
        f"(>= {min_resources} resources, >= {min_cluster_size} members).",
        "",
    ]
    for c in clusters:
        lines.append(f"--- {sorted(c.resources)}  (+{c.size} units) ---")
        for u in c.units:
            lang = f"[{u.language}] " if u.language else ""
            lines.append(f"    {lang}{u.location}::{u.name}")
        lines.append("")
    return "\n".join(lines)
