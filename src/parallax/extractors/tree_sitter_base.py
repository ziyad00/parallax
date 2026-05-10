"""Base class for tree-sitter-driven extractors.

Tree-sitter and its per-language grammar packages are optional. If they
are not installed, ``TreeSitterExtractor`` subclasses must not be
imported via the built-in registry; the package surface in
:mod:`parallax.extractors` registers them conditionally.
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..core import Unit
from .base import Extractor


class TreeSitterExtractor(Extractor):
    """Tree-sitter parser shared by language-specific subclasses."""

    file_extensions: tuple[str, ...] = ()
    language_name: str = ""
    ignore_dirs: set[str] = {"node_modules", "dist", "build", ".git", "__pycache__"}

    def _language(self) -> Any:
        raise NotImplementedError

    def _parser(self) -> Any:
        from tree_sitter import Parser

        return Parser(self._language())

    def _walk(self, root: Path) -> Iterator[Path]:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in self.file_extensions:
                continue
            if any(part in self.ignore_dirs for part in path.parts):
                continue
            yield path

    def extract(self, root: Path) -> Iterable[Unit]:
        parser = self._parser()
        units: list[Unit] = []
        for path in self._walk(root):
            try:
                source = path.read_bytes()
            except OSError:
                continue
            tree = parser.parse(source)
            rel = path.relative_to(root).as_posix()
            units.extend(self._units_from_tree(tree, source, rel))
        return units

    @abstractmethod
    def _units_from_tree(
        self, tree: Any, source: bytes, rel_path: str
    ) -> Iterable[Unit]:
        ...
