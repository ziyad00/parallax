"""Dart API-call extractor.

The ``http-urls`` extractor finds URL literals that appear verbatim in
source. Real Flutter codebases routinely build URLs by interpolating
constants from a central endpoints class::

    class ApiEndpoints {
      static const String follow = '/follow';
      static String cancelFollowRequest(int userId) =>
          '/follow/requests/$userId';
    }

    final path = '${ApiEndpoints.follow}/${requestModel.userId}';
    await _dio.delete(path);

The literal ``/follow/{id}`` never appears whole in the data source —
``http-urls`` only sees it inside ``ApiEndpoints``. That makes
cross-language clustering with backend routes weaker than it should be.

This extractor closes the gap. It scans every ``.dart`` file in two
passes:

1. Build a constant map for every class declaring members of the form
   ``static [const] String NAME = '...';`` or
   ``static String NAME(...) => '...';``. Keys are ``ClassName.member``.
2. Walk every Dart string literal. If the literal contains
   ``${ClassName.member}`` interpolation, substitute the constant
   value. Other ``$var`` / ``${var}`` interpolations collapse to
   ``{id}`` (matching the ``http-urls`` normalization). If the
   resolved string looks like a URL path, emit a Unit at the call site
   so the cluster includes the *consumer* file — which is where bugs
   like "data source uses the wrong endpoint constant" actually live.

Output resource format matches ``http-urls`` / ``fastapi-routes``
(path only, params collapsed to ``{id}``).
"""

from __future__ import annotations

import re
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
    ".next", ".nuxt",
    ".dart_tool",
    "build_runner",
}


# Matches `static [const] [Type?] NAME = '...';` inside a class body.
_CONST_RE = re.compile(
    r"""
    static\s+
    (?:const\s+)?
    (?:\w+\??\s+)?
    (?P<name>\w+)
    \s*=\s*
    (?P<quote>['"])
    (?P<value>(?:\\.|(?!(?P=quote)).)*)
    (?P=quote)
    \s*;
    """,
    re.VERBOSE,
)

# Matches `static [Type?] NAME([params]) => '...';` lambda-style getters.
_METHOD_RE = re.compile(
    r"""
    static\s+
    (?:\w+\??\s+)?
    (?P<name>\w+)
    \s*\([^)]*\)\s*=>\s*
    (?P<quote>['"])
    (?P<value>(?:\\.|(?!(?P=quote)).)*)
    (?P=quote)
    \s*;
    """,
    re.VERBOSE,
)

_CLASS_HEADER_RE = re.compile(r"\bclass\s+(\w+)\s*(?:extends\s+\w+\s*)?\{")

# Dart string literal — double or single quoted, with escape handling.
# Triple quotes / raw strings are uncommon in URL code and are skipped.
_STRING_LITERAL_RE = re.compile(
    r"""
    (?P<quote>['"])
    (?P<body>(?:\\.|(?!(?P=quote)).)*)
    (?P=quote)
    """,
    re.VERBOSE,
)

# ``${ClassName.member}`` — captures class + member separately for lookup.
# The trailing ``\}`` consumes the closing brace so substitution doesn't
# leave a stray ``}`` in the output.
_DOLLAR_BRACE_REF_RE = re.compile(r"\$\{([A-Z][A-Za-z0-9_]*)\.([A-Za-z_]\w*)\}")

# Bare ``$ident`` and ``${ident}`` (no class qualifier).
_BARE_DOLLAR_BRACE_RE = re.compile(r"\$\{[^}]+\}")
_BARE_DOLLAR_RE = re.compile(r"\$[A-Za-z_]\w*")


class DartApiCallExtractor(Extractor):
    """Resolve URL constants + interpolated calls in Dart source."""

    name = "dart-api-calls"

    def __init__(self, *, ignore_dirs: set[str] | None = None) -> None:
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS

    def extract(self, root: Path) -> Iterable[Unit]:
        return list(self._scan(root))

    def _walk(self, root: Path) -> Iterator[Path]:
        for p in root.rglob("*.dart"):
            if any(part in self.ignore_dirs for part in p.parts):
                continue
            yield p

    def _scan(self, root: Path) -> Iterator[Unit]:
        files = list(self._walk(root))
        constants = _collect_constants(files)
        if not constants:
            # No central endpoints class found; this extractor has nothing
            # useful to add. ``http-urls`` will still see plain literals.
            return

        for py in files:
            try:
                source = py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = py.relative_to(root).as_posix()

            seen: set[str] = set()
            for match in _STRING_LITERAL_RE.finditer(source):
                literal = match.group("body")
                # Only care about literals that reference the constant
                # map via ``${Class.member}``. Other ``$bar`` strings
                # are noise.
                if not _DOLLAR_BRACE_REF_RE.search(literal):
                    continue
                resolved = _resolve(literal, constants)
                normalized = _normalize_url(resolved)
                if not _looks_like_url_path(normalized):
                    continue
                if normalized in seen:
                    continue
                seen.add(normalized)
                line = source.count("\n", 0, match.start()) + 1
                yield Unit(
                    location=f"{rel}:{line}",
                    name=normalized,
                    resources=frozenset({normalized}),
                    language="dart",
                )


def _collect_constants(files: list[Path]) -> dict[str, str]:
    """Build ``"ClassName.member" -> raw_value`` for every static String member."""
    out: dict[str, str] = {}
    for py in files:
        try:
            source = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for class_match in _CLASS_HEADER_RE.finditer(source):
            class_name = class_match.group(1)
            body_open = class_match.end() - 1  # the `{` character index
            body_end = _matching_brace(source, body_open)
            if body_end is None:
                continue
            body = source[body_open + 1:body_end]
            for m in _CONST_RE.finditer(body):
                out[f"{class_name}.{m.group('name')}"] = m.group("value")
            for m in _METHOD_RE.finditer(body):
                out[f"{class_name}.{m.group('name')}"] = m.group("value")
    return out


def _matching_brace(source: str, open_idx: int) -> int | None:
    """Return the index of the ``}`` that closes the ``{`` at ``open_idx``."""
    if open_idx >= len(source) or source[open_idx] != "{":
        return None
    depth = 0
    for i in range(open_idx, len(source)):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _resolve(literal: str, constants: dict[str, str]) -> str:
    """Substitute ``${ClassName.member}`` refs with the constant's raw value.

    A constant whose value also contains interpolation is resolved
    recursively (with a visited set to avoid pathological loops). Bare
    ``$ident`` and ``${ident}`` collapse to ``{id}`` so a path like
    ``/follow/$userId`` normalizes to ``/follow/{id}``.
    """
    visited: set[str] = set()

    def sub_class_ref(match: re.Match) -> str:
        key = f"{match.group(1)}.{match.group(2)}"
        if key in visited or key not in constants:
            return "{id}"
        visited.add(key)
        try:
            return _resolve_inner(constants[key], constants, visited)
        finally:
            visited.discard(key)

    out = _DOLLAR_BRACE_REF_RE.sub(sub_class_ref, literal)
    out = _BARE_DOLLAR_BRACE_RE.sub("{id}", out)
    out = _BARE_DOLLAR_RE.sub("{id}", out)
    return out


def _resolve_inner(literal: str, constants: dict[str, str], visited: set[str]) -> str:
    def sub_class_ref(match: re.Match) -> str:
        key = f"{match.group(1)}.{match.group(2)}"
        if key in visited or key not in constants:
            return "{id}"
        visited.add(key)
        try:
            return _resolve_inner(constants[key], constants, visited)
        finally:
            visited.discard(key)

    out = _DOLLAR_BRACE_REF_RE.sub(sub_class_ref, literal)
    out = _BARE_DOLLAR_BRACE_RE.sub("{id}", out)
    out = _BARE_DOLLAR_RE.sub("{id}", out)
    return out


def _normalize_url(path: str) -> str:
    """Match ``HttpUrlExtractor.normalize_url`` so clusters merge cleanly."""
    if "://" in path:
        after_host = path.split("://", 1)[1]
        slash = after_host.find("/")
        path = after_host[slash:] if slash >= 0 else "/"
    for sep in "?#":
        if sep in path:
            path = path.split(sep, 1)[0]
    path = re.sub(r"/\{[^}/]+\}", "/{id}", path)
    path = re.sub(r"/\d+", "/{id}", path)
    if path.endswith("/") and len(path) > 1:
        path = path[:-1]
    return path


def _looks_like_url_path(s: str) -> bool:
    """Conservative filter: starts with ``/``, has at least two segments,
    no whitespace, no embedded quotes."""
    if not s.startswith("/") or "/" not in s[1:]:
        return False
    if any(c.isspace() for c in s):
        return False
    if any(c in s for c in ("'", '"', "`")):
        return False
    return True
