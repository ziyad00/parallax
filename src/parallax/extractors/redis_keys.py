"""Redis-key extractor — language-agnostic.

For each text source file, the unit's resource set is the set of Redis
key *prefixes* it reads from or writes to. Picks up calls like:

- Python (``redis-py``, ``aioredis``, ``redis.asyncio``):
  ``r.get("user:42:profile")``, ``await r.set("session:abc", ...)``,
  ``client.hget("group:7", "members")``
- JS / TS (``ioredis``, ``node-redis``):
  ``await redis.get("key:..")``, ``redis.set("key:..", v)``
- Go (``go-redis``): ``rdb.Get(ctx, "user:42")``
- Generic ``GET key:foo``, ``SET key:bar`` in shell scripts.

Keys are normalised by replacing dynamic path segments (numbers, UUIDs,
``{var}`` placeholders, f-string expressions) with ``{id}`` so calls
reading/writing the same logical key cluster together.

The colon convention (``namespace:id:field``) is the most universal
Redis key style, so the prefix-only mode keys on the leading
namespace component (everything up to the first ``:``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator

from ..core import Unit
from .base import Extractor
from .http_urls import (
    DEFAULT_IGNORE_DIRS as _SHARED_IGNORE,
    DEFAULT_TEXT_EXTENSIONS as _SHARED_TEXT_EXT,
    _language_from_suffix,
)


# Match calls like .get("..."), .set("...", ...), .hget("...", ...) etc.
# Captures the first string argument, which is the redis key.
_REDIS_OPS = (
    "get",
    "set",
    "setex",
    "setnx",
    "del",
    "exists",
    "expire",
    "incr",
    "incrby",
    "decr",
    "hget",
    "hset",
    "hdel",
    "hgetall",
    "hkeys",
    "hvals",
    "lpush",
    "rpush",
    "lpop",
    "rpop",
    "llen",
    "sadd",
    "smembers",
    "srem",
    "sismember",
    "zadd",
    "zrange",
    "zrem",
)
_REDIS_OPS_PATTERN = "|".join(_REDIS_OPS)

# Default allow-list of receiver names that look like a Redis client.
# We match ``<receiver>.<op>("key", ...)`` where ``<receiver>`` is one
# of these. Adding ``await`` and other prefixes is fine — the regex is
# anchored to the dot-call boundary, not the start of the line.
DEFAULT_REDIS_RECEIVERS = frozenset({
    "r",
    "rdb",
    "redis",
    "redis_client",
    "client",
    "cache",
    "kv",
    "conn",
    "connection",
    "_redis",
    "_cache",
    "self.redis",
    "self.cache",
    "self.client",
    "self._redis",
    "self._cache",
})


def _build_key_re(receivers: frozenset[str]) -> re.Pattern[str]:
    """Build the pattern that gates redis-key extraction by receiver name.

    Without this gate, calls like ``params.get('foo')``, ``dict.set(...)``,
    or ``set.add(...)`` would all be misclassified as Redis ops. The
    audit on a real Python codebase showed these false positives
    dominate the output.
    """
    receiver_alt = "|".join(sorted({re.escape(r) for r in receivers}, key=len, reverse=True))
    return re.compile(
        rf"""(?:{receiver_alt})\s*\.\s*(?:{_REDIS_OPS_PATTERN})\s*\(\s*[fFrRbBuU]{{0,2}}[\"'`]([^\"'`]+)[\"'`]""",
        re.IGNORECASE,
    )


class RedisKeysExtractor(Extractor):
    """Find files that touch the same Redis key namespaces."""

    name = "redis-keys"

    def __init__(
        self,
        *,
        text_extensions: set[str] | None = None,
        ignore_dirs: set[str] | None = None,
        prefix_only: bool = True,
        receivers: frozenset[str] | None = None,
    ) -> None:
        self.text_extensions = text_extensions or _SHARED_TEXT_EXT
        self.ignore_dirs = ignore_dirs or _SHARED_IGNORE
        self.prefix_only = prefix_only
        self.receivers = receivers or DEFAULT_REDIS_RECEIVERS
        self._key_re = _build_key_re(self.receivers)

    def extract(self, root: Path) -> Iterable[Unit]:
        return list(self._scan(root))

    def _scan(self, root: Path) -> Iterator[Unit]:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in self.ignore_dirs for part in path.parts):
                continue
            if path.suffix not in self.text_extensions:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            keys: set[str] = set()
            for m in self._key_re.finditer(text):
                keys.add(self.normalize_key(m.group(1)))

            if keys:
                rel = path.relative_to(root).as_posix()
                yield Unit(
                    location=rel,
                    name=path.name,
                    resources=frozenset(keys),
                    language=_language_from_suffix(path.suffix),
                )

    def normalize_key(self, raw: str) -> str:
        """Reduce a raw key match to a stable namespace identifier."""
        # Replace numeric segments with {id}.
        key = re.sub(r"\d+", "{id}", raw)
        # Replace simple Python f-string interpolation tokens.
        key = re.sub(r"\{[^}]*\}", "{id}", key)
        if self.prefix_only and ":" in key:
            return key.split(":", 1)[0]
        return key
