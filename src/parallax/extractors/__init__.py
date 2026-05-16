"""Resource extractors."""

from .base import Extractor
from .dart_api_calls import DartApiCallExtractor
from .django_models import DjangoExtractor
from .env_vars import EnvVarsExtractor
from .fastapi_routes import FastApiRoutesExtractor
from .http_urls import HttpUrlExtractor
from .redis_keys import RedisKeysExtractor
from .sqlalchemy_models import SqlAlchemyExtractor

__all__ = [
    "Extractor",
    "DartApiCallExtractor",
    "DjangoExtractor",
    "EnvVarsExtractor",
    "FastApiRoutesExtractor",
    "HttpUrlExtractor",
    "RedisKeysExtractor",
    "SqlAlchemyExtractor",
    "BUILTIN_EXTRACTORS",
]

BUILTIN_EXTRACTORS: dict[str, type[Extractor]] = {
    "sqlalchemy": SqlAlchemyExtractor,
    "django": DjangoExtractor,
    "fastapi-routes": FastApiRoutesExtractor,
    "dart-api-calls": DartApiCallExtractor,
    "http-urls": HttpUrlExtractor,
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
