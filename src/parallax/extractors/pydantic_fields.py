"""Pydantic / dataclass field extractor.

Walks Python source for ``class X(BaseModel):`` (and ``@dataclass``)
declarations and emits one :class:`~parallax.core.Unit` per declared
field. Resource is the field name only — so a backend Pydantic field
``is_followed`` clusters with any Dart ``json['is_followed']`` access
emitted by ``dart-json-fields``.

Singleton clusters in either direction indicate response-shape drift:

* A Pydantic field with no Dart reader → frontend ignores it
  (acceptable) OR frontend renamed the wire field (bug).
* A Dart ``json['X']`` with no Pydantic field → frontend reads
  something the backend never serialises (bug).

Common ubiquitous fields (``id``, ``name``, ``created_at``) end up in
large matched clusters and aren't the signal; the signal is the
single-language outliers.
"""

from __future__ import annotations

import ast
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
    "migrations",
    "tests",
}

# Class-name suffixes that suggest a response/wire shape. Restricting
# to these keeps the report focused on the surface area frontends
# actually read.
RESPONSE_NAME_HINTS = (
    "Response",
    "Schema",
    "Model",
    "Out",
    "DTO",
    "Payload",
)


class PydanticFieldsExtractor(Extractor):
    """Emit one Unit per declared field on a Pydantic / dataclass / response
    shape class."""

    name = "pydantic-fields"

    def __init__(
        self,
        *,
        ignore_dirs: set[str] | None = None,
        response_name_hints: tuple[str, ...] = RESPONSE_NAME_HINTS,
    ) -> None:
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        self.response_name_hints = response_name_hints

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
                if not isinstance(node, ast.ClassDef):
                    continue
                if not self._is_response_shape(node):
                    continue
                for item in node.body:
                    field = _field_name(item)
                    if not field:
                        continue
                    yield Unit(
                        location=f"{rel}:{item.lineno}",
                        name=f"{node.name}.{field}",
                        resources=frozenset({field}),
                        language="python",
                        extra={"class": node.name, "field": field},
                    )

    def _is_response_shape(self, cls: ast.ClassDef) -> bool:
        # Inherits BaseModel anywhere on the MRO line we can see?
        for base in cls.bases:
            if _base_name(base) in {"BaseModel", "BaseSettings"}:
                return True
        # @dataclass decorator?
        for dec in cls.decorator_list:
            name = _decorator_name(dec)
            if name == "dataclass":
                return True
        # Heuristic name suffix — picks up plain classes that happen to
        # be wire shapes without inheriting Pydantic (e.g. TypedDict
        # patterns, or projects that use plain classes for response models).
        return any(cls.name.endswith(suffix) for suffix in self.response_name_hints)


def _field_name(node: ast.stmt) -> str | None:
    """Return the field name for declarations we want to track.

    ``foo: int`` and ``foo: int = 0`` both count. ``foo = 0`` without
    a type annotation is skipped — too ambiguous to treat as a wire
    field. Method definitions and inner classes are skipped.
    """
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return _base_name(node)
