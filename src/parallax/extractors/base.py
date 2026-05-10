"""Extractor interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from ..core import Unit


class Extractor(ABC):
    """Scan a source tree and yield :class:`~parallax.core.Unit` records.

    Implementations should be stateless, idempotent, and skip files
    that fail to parse rather than aborting the whole run.
    """

    name: str

    @abstractmethod
    def extract(self, root: Path) -> Iterable[Unit]:
        """Walk ``root`` and yield zero or more units per file."""
