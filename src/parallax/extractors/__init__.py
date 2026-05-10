"""Extractors — pluggable resource detectors per framework / domain / language."""

from .base import Extractor
from .django_models import DjangoExtractor
from .http_urls import HttpUrlExtractor
from .sqlalchemy_models import SqlAlchemyExtractor

__all__ = [
    "Extractor",
    "DjangoExtractor",
    "HttpUrlExtractor",
    "SqlAlchemyExtractor",
    "BUILTIN_EXTRACTORS",
]

BUILTIN_EXTRACTORS: dict[str, type[Extractor]] = {
    "sqlalchemy": SqlAlchemyExtractor,
    "django": DjangoExtractor,
    "http-urls": HttpUrlExtractor,
}
