"""parallax: find code that does the same logical job through different paths."""

from .core import (
    Cluster,
    FoldedGroup,
    Unit,
    fold_units_by_class,
    group_by_resource_set,
)
from .extractors.base import Extractor

__all__ = [
    "Cluster",
    "Extractor",
    "FoldedGroup",
    "Unit",
    "fold_units_by_class",
    "group_by_resource_set",
]
__version__ = "0.3.0"
