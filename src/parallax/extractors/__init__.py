"""Extractors — pluggable resource detectors per framework / domain / language."""

from .base import Extractor
from .http_urls import HttpUrlExtractor
from .sqlalchemy_models import SqlAlchemyExtractor

__all__ = [
    "Extractor",
    "HttpUrlExtractor",
    "SqlAlchemyExtractor",
    "BUILTIN_EXTRACTORS",
]

BUILTIN_EXTRACTORS: dict[str, type[Extractor]] = {
    "sqlalchemy": SqlAlchemyExtractor,
    "http-urls": HttpUrlExtractor,
}
