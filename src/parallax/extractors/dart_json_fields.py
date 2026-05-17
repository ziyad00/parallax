"""Dart JSON-field extractor.

Pairs with ``pydantic-fields``. Walks every ``.dart`` file looking
for ``json['X']`` / ``json["X"]`` accesses inside ``fromJson``-style
factory methods, and emits one :class:`~parallax.core.Unit` per
distinct (file × field) pair.

Resource is the field-name string, matching the Pydantic extractor's
shape, so backend and frontend cluster on the same key.

Implementation is intentionally regex-based — Dart parsing for a
sliver of field-name extraction isn't worth a tree-sitter dependency.
The pattern only matches ``json['ident']`` accesses (single or double
quotes, with escapes), which is the dominant Flutter idiom.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator

from ..core import Unit
from .base import Extractor


DEFAULT_IGNORE_DIRS = {
    ".dart_tool",
    "build",
    ".git",
    "node_modules",
}

# Files matching any of these path fragments are skipped wholesale.
# Local-storage / cache helper classes round-trip JSON for on-disk
# persistence in a shape that has nothing to do with the wire format,
# and they bury the real-drift signal under camelCase / snake_case
# duplicates that are correct by design. Override via the
# ``ignore_path_patterns`` constructor arg if your codebase needs
# something different.
DEFAULT_IGNORE_PATH_PATTERNS = (
    "_local_storage.dart",
    "/local/",  # any class under data_sources/local/ etc.
    "_cache_helper.dart",
    "ProfileCacheHelper.dart",
    "TrendingPageCacheHelper.dart",
)


# Matches:
#   json['field']
#   json["field"]
# inside any code. We deliberately don't insist on the surrounding
# ``fromJson`` context — practical Dart code reads ``json[k]`` outside
# factory methods too, and the field-name signal is the same.
_JSON_KEY_RE = re.compile(
    r"""
    \bjson\s*\[\s*
    (?P<quote>['"])
    (?P<key>(?:\\.|(?!(?P=quote)).)+)
    (?P=quote)
    \s*\]
    """,
    re.VERBOSE,
)


class DartJsonFieldsExtractor(Extractor):
    """Emit one Unit per (file, json key) pair in Dart source."""

    name = "dart-json-fields"

    def __init__(
        self,
        *,
        ignore_dirs: set[str] | None = None,
        ignore_path_patterns: Iterable[str] = DEFAULT_IGNORE_PATH_PATTERNS,
    ) -> None:
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        self.ignore_path_patterns = tuple(ignore_path_patterns)

    def extract(self, root: Path) -> Iterable[Unit]:
        return list(self._scan(root))

    def _walk(self, root: Path) -> Iterator[Path]:
        for p in root.rglob("*.dart"):
            if any(part in self.ignore_dirs for part in p.parts):
                continue
            posix = p.as_posix()
            if any(pat in posix for pat in self.ignore_path_patterns):
                continue
            yield p

    def _scan(self, root: Path) -> Iterator[Unit]:
        for dart in self._walk(root):
            try:
                text = dart.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = dart.relative_to(root).as_posix()
            seen: dict[str, int] = {}
            for match in _JSON_KEY_RE.finditer(text):
                key = match.group("key")
                if key in seen:
                    continue
                seen[key] = text.count("\n", 0, match.start()) + 1

            for key, line in seen.items():
                yield Unit(
                    location=f"{rel}:{line}",
                    name=key,
                    resources=frozenset({key}),
                    language="dart",
                    extra={"field": key},
                )
