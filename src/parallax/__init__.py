"""parallax — find code that does the same logical job through different paths.

Language-, unit-, and resource-agnostic. Pluggable extractors per
framework / domain / language; a common grouping engine.
"""

from .core import Unit, Cluster, group_by_resource_set
from .extractors.base import Extractor

__all__ = ["Unit", "Cluster", "group_by_resource_set", "Extractor"]
__version__ = "0.1.0"
