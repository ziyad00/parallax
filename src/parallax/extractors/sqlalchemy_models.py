"""SQLAlchemy ORM extractor.

Resources are classes inheriting from a declarative ``Base``. Each
function or method emits a :class:`~parallax.core.Unit` whose
resource set is the model classes it references.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, Iterator

from ..core import Unit
from .base import Extractor


# Files we never scan: typically codegen, vendor, or migration noise.
DEFAULT_IGNORE_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    "node_modules",
    "alembic",
    "dist",
    "build",
}


class SqlAlchemyExtractor(Extractor):
    """Find Python functions whose body references SQLAlchemy model classes."""

    name = "sqlalchemy"

    def __init__(
        self,
        *,
        base_class: str = "Base",
        ignore_dirs: set[str] | None = None,
    ) -> None:
        self.base_class = base_class
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS

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
        models: set[str] = set()
        for py in self._walk(root):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
                    if self.base_class in bases:
                        models.add(node.name)
        return models

    def _scan(self, root: Path, models: set[str]) -> Iterator[Unit]:
        for py in self._walk(root):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = py.relative_to(root).as_posix()
            yield from _units_in_tree(tree, rel, models)


def _units_in_tree(
    tree: ast.AST, rel_path: str, models: set[str]
) -> Iterator[Unit]:
    class_stack: list[str] = []

    def visit(node: ast.AST) -> Iterator[Unit]:
        if isinstance(node, ast.ClassDef):
            class_stack.append(node.name)
            for child in node.body:
                yield from visit(child)
            class_stack.pop()
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            resources = _collect_referenced_names(node, models)
            if resources:
                qualified = (
                    f"{class_stack[-1]}.{node.name}" if class_stack else node.name
                )
                lineno = getattr(node, "lineno", 0)
                yield Unit(
                    location=f"{rel_path}:{lineno}",
                    name=qualified,
                    resources=frozenset(resources),
                    language="python",
                )

    for top in tree.body:  # type: ignore[attr-defined]
        yield from visit(top)


def _collect_referenced_names(node: ast.AST, models: set[str]) -> set[str]:
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in models:
            found.add(child.id)
        elif isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
            if child.value.id in models:
                found.add(child.value.id)
    return found
