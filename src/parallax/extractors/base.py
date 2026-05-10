"""Extractor interface — language-, unit-, and resource-agnostic.

An extractor scans a source tree (any language, any framework) and
yields :class:`~parallax.core.Unit` records. The shipping extractors
live alongside this module:

- :class:`SqlAlchemyExtractor` — Python AST + SQLAlchemy ORM models
- :class:`HttpUrlExtractor` — regex-based detection of HTTP URLs in any
  textual source file (Python, TS, Go, shell, YAML, ...)

Future extractors (Django, Sequelize, tree-sitter for arbitrary
languages, Terraform, Kafka topic publishers, Redis key prefixes,
microservice manifests, ...) only need to implement :meth:`extract`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from ..core import Unit


class Extractor(ABC):
    """Identify units of code and the resources they touch.

    Implementations must be:

    - **Stateless**: pure function of the input tree.
    - **Idempotent**: calling :meth:`extract` twice on the same tree
      returns the same units.
    - **Robust to syntax errors**: skip files that don't parse rather
      than crashing the whole run.
    """

    name: str  # short identifier, e.g. "sqlalchemy", "http-urls", "terraform"

    @abstractmethod
    def extract(self, root: Path) -> Iterable[Unit]:
        """Walk ``root`` and yield Unit records (zero or more per file)."""
