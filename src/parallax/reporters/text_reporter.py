"""Plain-text output."""

from __future__ import annotations

from typing import Iterable

from ..core import Cluster, FoldedGroup, fold_units_by_class


def render_text(
    clusters: Iterable[Cluster],
    *,
    scanned_units: int,
    extractors: list[str],
    min_resources: int,
    min_cluster_size: int,
    fold_threshold: int = 5,
) -> str:
    clusters = list(clusters)
    lines: list[str] = [
        f"Scanned {scanned_units} units (extractors: {', '.join(extractors)}). "
        f"Found {len(clusters)} clusters "
        f"(>= {min_resources} resources, >= {min_cluster_size} members).",
        "",
    ]
    for c in clusters:
        sim_label = (
            f", names {c.name_similarity:.0%} similar"
            if c.name_similarity >= 0.5
            else ""
        )
        lines.append(
            f"--- {sorted(c.resources)}  (+{c.size} units, "
            f"score {c.score:.2f}{sim_label}) ---"
        )
        for entry in fold_units_by_class(c.units, threshold=fold_threshold):
            if isinstance(entry, FoldedGroup):
                preview = ", ".join(entry.method_names[:4])
                more = (
                    f", +{entry.method_count - 4} more"
                    if entry.method_count > 4
                    else ""
                )
                lines.append(
                    f"    [{entry.language}] {entry.location} :: "
                    f"{entry.class_name} ({entry.method_count} methods: "
                    f"{preview}{more})"
                )
            else:
                lang = f"[{entry.language}] " if entry.language else ""
                lines.append(f"    {lang}{entry.location}::{entry.name}")
        lines.append("")
    return "\n".join(lines)
