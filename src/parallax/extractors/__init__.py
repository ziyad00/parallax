"""Extractors — pluggable resource detectors per framework / domain / language."""

from .base import Extractor
from .django_models import DjangoExtractor
from .env_vars import EnvVarsExtractor
from .http_urls import HttpUrlExtractor
from .redis_keys import RedisKeysExtractor
from .sqlalchemy_models import SqlAlchemyExtractor

__all__ = [
    "Extractor",
    "DjangoExtractor",
    "EnvVarsExtractor",
    "HttpUrlExtractor",
    "RedisKeysExtractor",
    "SqlAlchemyExtractor",
    "BUILTIN_EXTRACTORS",
]

BUILTIN_EXTRACTORS: dict[str, type[Extractor]] = {
    "sqlalchemy": SqlAlchemyExtractor,
    "django": DjangoExtractor,
    "http-urls": HttpUrlExtractor,
    "env-vars": EnvVarsExtractor,
    "redis-keys": RedisKeysExtractor,
}
