"""Django ORM extractor.

Treats every Python class inheriting from ``models.Model`` (or
``django.db.models.Model``) as a "resource." For each function or
method in the source tree, the unit's resource set is the set of
Django model class names it references.

Mirrors :class:`SqlAlchemyExtractor` but for Django apps. Two views or
managers querying the same set of models therefore land in the same
cluster, even if the surface code differs (raw QuerySet, manager
methods, get_object_or_404, etc.).
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
        # ``migrations/`` is the only Django-specific path worth filtering:
        # migration files re-import models cosmetically and would inflate
        # the cluster signal. ``fixtures/`` / ``static/`` / ``media/``
        # are non-Python so the .py glob filters them anyway, and the
        # ``fixtures`` name collides with test-fixture directories.
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
    """True if any base looks like ``models.Model`` or ``Model``-derived.

    Catches:
    - class Foo(models.Model): ...
    - class Foo(Model): ...                 (when ``Model`` is imported)
    - class Foo(django.db.models.Model): ...
    - class Foo(BaseModel, models.Model): ... (multiple bases)
    """
    for base in cls.bases:
        if _base_is_django_model(base):
            return True
    return False


def _base_is_django_model(node: ast.expr) -> bool:
    if isinstance(node, ast.Name) and node.id in {"Model", "models"}:
        # Bare ``Model`` could be Django; we accept it. Risk of false
        # positive (e.g. pydantic's BaseModel). The cluster grouping
        # filters via min_resources / min_cluster_size limits damage.
        return node.id == "Model"
    if isinstance(node, ast.Attribute):
        # models.Model
        if node.attr == "Model" and isinstance(node.value, ast.Name) and node.value.id == "models":
            return True
        # django.db.models.Model
        if node.attr == "Model":
            return _is_models_attribute_chain(node.value)
    return False


def _is_models_attribute_chain(node: ast.expr) -> bool:
    """True if ``node`` resolves to the ``models`` submodule of django.db."""
    if isinstance(node, ast.Attribute) and node.attr == "models":
        # x.models — accept if x looks like django.db
        return True
    if isinstance(node, ast.Name) and node.id == "models":
        return True
    return False
