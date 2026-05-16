"""parallax: find code that does the same logical job through different paths."""

from .axis_coverage import AxisGroup, axis_coverage, render_axis_report
from .core import (
    Cluster,
    FoldedGroup,
    Unit,
    fold_units_by_class,
    group_by_resource_set,
)
from .extractors.base import Extractor

__all__ = [
    "AxisGroup",
    "Cluster",
    "Extractor",
    "FoldedGroup",
    "Unit",
    "axis_coverage",
    "fold_units_by_class",
    "group_by_resource_set",
    "render_axis_report",
]
__version__ = "0.4.0"
