"""Django ORM extractor.

Resources are classes inheriting from ``models.Model`` (or fully
qualified ``django.db.models.Model``). Each function or method emits
a :class:`~parallax.core.Unit` whose resource set is the model
classes it references.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, Iterator

from ..core import Unit
from .base import Extractor
from .sqlalchemy_models import (
    DEFAULT_IGNORE_DIRS,
    _collect_referenced_names,
    _units_in_tree,
)


class DjangoExtractor(Extractor):
    """Find Python functions whose body references Django ORM model classes."""

    name = "django"

    def __init__(self, *, ignore_dirs: set[str] | None = None) -> None:
        # ``migrations/`` is excluded because migration files re-import
        # models cosmetically and inflate the signal.
        self.ignore_dirs = (ignore_dirs or DEFAULT_IGNORE_DIRS) | {"migrations"}

    def extract(self, root: Path) -> Iterable[Unit]:
        models = self._discover_models(root)
        if not models:
            return []
        return list(self._scan(root, models))

    def _walk(self, root: Path) -> Iterator[Path]:
        for p in root.rglob("*.py"):
            if any(part in self.ignore_dirs for part in p.parts):
                continue
            if p.name == "__init__.py":
                continue
            yield p

    def _discover_models(self, root: Path) -> set[str]:
        """Find every class whose base list mentions ``models.Model``."""
        out: set[str] = set()
        for py in self._walk(root):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and _inherits_django_model(node):
                    out.add(node.name)
        return out

    def _scan(self, root: Path, models: set[str]) -> Iterator[Unit]:
        for py in self._walk(root):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = py.relative_to(root).as_posix()
            yield from _units_in_tree(tree, rel, models)


def _inherits_django_model(cls: ast.ClassDef) -> bool:
    return any(_base_is_django_model(b) for b in cls.bases)


def _base_is_django_model(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "Model"
    if isinstance(node, ast.Attribute) and node.attr == "Model":
        if isinstance(node.value, ast.Name) and node.value.id == "models":
            return True
        return _is_models_attribute_chain(node.value)
    return False


def _is_models_attribute_chain(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "models":
        return True
    if isinstance(node, ast.Name) and node.id == "models":
        return True
    return False
