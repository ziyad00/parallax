"""Cache-key set/invalidate symmetry.

Most caches in real services have a contract: every write to a key
should be paired with at least one invalidation site elsewhere. When
that pairing breaks — a new write is added but no one invalidates the
key, or vice versa — the result is stale-read bugs that survive every
unit test, because the test path either always writes or always reads.

This extractor emits one Unit per recognised cache call. Resources
encode both the *operation* and the *key prefix*, so a missing
counterpart shows up as a singleton cluster::

    Set: ``set:profile_counts``
    Invalidate: ``invalidate:profile_counts``

Both touching ``profile_counts`` cluster together — symmetric.
Either appearing alone is suspicious.

Recognised call shapes (configurable via ``call_specs``):

* ``cache.set(KEY, value, ...)``
* ``cache.invalidate(KEY, ...)``
* ``cache.set_user(user_id, KEY, value, ...)``
* ``cache.invalidate_user(user_id, KEY, ...)``
* ``response_cache.set(KEY, value, ttl)``

The recogniser is purely syntactic — it matches by method name and
the first/second positional arg's string literal. f-strings like
``f"liked_checkin:{id}"`` are captured by their literal prefix
(``liked_checkin``); pure variable / computed keys are skipped.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from ..core import Unit
from .base import Extractor


DEFAULT_IGNORE_DIRS = {
    "__pycache__",
    ".venv", "venv",
    ".git",
    "node_modules",
    "dist", "build", "target",
    "tests",  # test fixtures often write keys nobody else invalidates
    "migrations",
}


@dataclass(frozen=True)
class CacheCallSpec:
    """One recognised cache method.

    ``method_name`` — attribute being called (``set``, ``invalidate``...).
    ``key_arg_index`` — positional index of the key argument.
    ``op`` — semantic op printed in the resource prefix; ``set`` /
    ``invalidate`` are the two we care about.
    """

    method_name: str
    key_arg_index: int
    op: str


DEFAULT_CALL_SPECS: tuple[CacheCallSpec, ...] = (
    CacheCallSpec("set", 0, "set"),
    CacheCallSpec("invalidate", 0, "invalidate"),
    CacheCallSpec("set_user", 1, "set"),
    CacheCallSpec("invalidate_user", 1, "invalidate"),
)


class CacheKeysExtractor(Extractor):
    """Find cache set/invalidate calls and emit per-(op, key) Units."""

    name = "cache-keys"

    def __init__(
        self,
        *,
        ignore_dirs: set[str] | None = None,
        call_specs: Iterable[CacheCallSpec] = DEFAULT_CALL_SPECS,
    ) -> None:
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        self._specs_by_name = {s.method_name: s for s in call_specs}

    def extract(self, root: Path) -> Iterable[Unit]:
        return list(self._scan(root))

    def _walk(self, root: Path) -> Iterator[Path]:
        for p in root.rglob("*.py"):
            if any(part in self.ignore_dirs for part in p.parts):
                continue
            yield p

    def _scan(self, root: Path) -> Iterator[Unit]:
        for py in self._walk(root):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            rel = py.relative_to(root).as_posix()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute):
                    continue
                spec = self._specs_by_name.get(func.attr)
                if spec is None:
                    continue
                key = _extract_literal_prefix(node, spec.key_arg_index)
                if key is None:
                    continue
                yield Unit(
                    location=f"{rel}:{node.lineno}",
                    name=f"{spec.op}:{key}",
                    resources=frozenset({f"{spec.op}:{key}"}),
                    language="python",
                    extra={"op": spec.op, "key": key, "method": func.attr},
                )


def _extract_literal_prefix(call: ast.Call, arg_index: int) -> str | None:
    """Pull the cache key out of a call's positional arg.

    Plain strings come back unchanged. JoinedStr (f-strings) collapse
    to the literal prefix so ``f"liked_checkin:{id}"`` returns
    ``liked_checkin``. Computed keys (variables, function calls) are
    rejected — too opaque to compare.
    """
    if len(call.args) <= arg_index:
        return None
    arg = call.args[arg_index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr) and arg.values:
        first = arg.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value.rstrip(":")
    return None
