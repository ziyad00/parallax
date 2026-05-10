"""SQLAlchemy ORM extractor.

Resources are classes inheriting from a declarative ``Base``. Each
function or method emits a :class:`~parallax.core.Unit` whose
resource set is the model classes it references.

When ``follow_repos`` is enabled, calls into repository classes
(name ending in ``Repository``) also contribute the models that
repository touches, so callers cluster with inline-query siblings.
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
        follow_repos: bool = True,
        repo_class_suffix: str = "Repository",
    ) -> None:
        self.base_class = base_class
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        self.follow_repos = follow_repos
        self.repo_class_suffix = repo_class_suffix

    def extract(self, root: Path) -> Iterable[Unit]:
        models = self._discover_models(root)
        if not models:
            return []
        repo_methods: dict[str, frozenset[str]] = {}
        if self.follow_repos:
            repo_methods = self._discover_repo_methods(root, models)
        return list(self._scan(root, models, repo_methods))

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

    def _discover_repo_methods(
        self, root: Path, models: set[str]
    ) -> dict[str, frozenset[str]]:
        """Map ``method_name`` to the model set its repository method touches.

        Repositories are classes whose name ends with ``self.repo_class_suffix``.
        When the same method name appears on multiple repositories, the
        method's resources become the union of all owners — heuristic
        but the cluster engine then absorbs the noise via its scoring.
        """
        out: dict[str, set[str]] = {}
        for py in self._walk(root):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                if not node.name.endswith(self.repo_class_suffix):
                    continue
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        resources = _collect_referenced_names(child, models)
                        if resources:
                            out.setdefault(child.name, set()).update(resources)
        return {k: frozenset(v) for k, v in out.items()}

    def _scan(
        self,
        root: Path,
        models: set[str],
        repo_methods: dict[str, frozenset[str]],
    ) -> Iterator[Unit]:
        for py in self._walk(root):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            rel = py.relative_to(root).as_posix()
            yield from _units_in_tree(tree, rel, models, repo_methods)


def _units_in_tree(
    tree: ast.AST,
    rel_path: str,
    models: set[str],
    repo_methods: dict[str, frozenset[str]] | None = None,
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
            if repo_methods:
                resources |= _collect_repo_call_resources(node, repo_methods)
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


def _collect_repo_call_resources(
    node: ast.AST, repo_methods: dict[str, frozenset[str]]
) -> set[str]:
    """Find ``<receiver>.<method>(...)`` calls whose method matches a
    known repository method, and return the union of those methods'
    resources."""
    found: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        method_name: str | None = None
        if isinstance(func, ast.Attribute):
            method_name = func.attr
        if method_name and method_name in repo_methods:
            found |= repo_methods[method_name]
    return found
