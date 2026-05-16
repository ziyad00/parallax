"""Resource extractors."""

from .base import Extractor
from .cache_keys import CacheKeysExtractor
from .dart_api_calls import DartApiCallExtractor
from .dart_json_fields import DartJsonFieldsExtractor
from .django_models import DjangoExtractor
from .env_vars import EnvVarsExtractor
from .fastapi_routes import FastApiRoutesExtractor
from .http_urls import HttpUrlExtractor
from .pydantic_fields import PydanticFieldsExtractor
from .redis_keys import RedisKeysExtractor
from .sqlalchemy_models import SqlAlchemyExtractor

__all__ = [
    "Extractor",
    "CacheKeysExtractor",
    "DartApiCallExtractor",
    "DartJsonFieldsExtractor",
    "DjangoExtractor",
    "EnvVarsExtractor",
    "FastApiRoutesExtractor",
    "HttpUrlExtractor",
    "PydanticFieldsExtractor",
    "RedisKeysExtractor",
    "SqlAlchemyExtractor",
    "BUILTIN_EXTRACTORS",
]

BUILTIN_EXTRACTORS: dict[str, type[Extractor]] = {
    "sqlalchemy": SqlAlchemyExtractor,
    "django": DjangoExtractor,
    "fastapi-routes": FastApiRoutesExtractor,
    "dart-api-calls": DartApiCallExtractor,
    "dart-json-fields": DartJsonFieldsExtractor,
    "http-urls": HttpUrlExtractor,
    "pydantic-fields": PydanticFieldsExtractor,
    "cache-keys": CacheKeysExtractor,
    "env-vars": EnvVarsExtractor,
    "redis-keys": RedisKeysExtractor,
}

try:
    from .sequelize import SequelizeExtractor
except ImportError:
    pass
else:
    __all__.append("SequelizeExtractor")
    BUILTIN_EXTRACTORS["sequelize"] = SequelizeExtractor
