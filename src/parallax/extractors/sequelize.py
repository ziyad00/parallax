"""TypeScript / JavaScript Sequelize + TypeORM model extractor.

Resources are entity classes detected in the source: TypeORM
``@Entity()``-decorated classes, classes extending ``Model`` from
``sequelize``, and ``sequelize.define('Name', ...)`` calls.

Each function or method emits a :class:`~parallax.core.Unit` whose
resource set is the entity names it references.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Iterator

from ..core import Unit
from .tree_sitter_base import TreeSitterExtractor


class SequelizeExtractor(TreeSitterExtractor):
    name = "sequelize"
    file_extensions = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
    language_name = "typescript"

    def _language(self) -> Any:
        from tree_sitter import Language
        import tree_sitter_typescript

        return Language(tree_sitter_typescript.language_typescript())

    def extract(self, root: Path) -> Iterable[Unit]:
        parser = self._parser()
        entities: set[str] = set()
        parsed: list[tuple[Path, Any, bytes]] = []
        for path in self._walk(root):
            try:
                source = path.read_bytes()
            except OSError:
                continue
            tree = parser.parse(source)
            parsed.append((path, tree, source))
            entities.update(_discover_entities(tree.root_node, source))

        if not entities:
            return []

        units: list[Unit] = []
        for path, tree, source in parsed:
            rel = path.relative_to(root).as_posix()
            units.extend(_units_in_tree(tree.root_node, source, rel, entities))
        return units

    def _units_from_tree(
        self, tree: Any, source: bytes, rel_path: str
    ) -> Iterable[Unit]:
        return []


def _text(node: Any, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _discover_entities(root: Any, source: bytes) -> Iterator[str]:
    for parent in _walk(root):
        children = parent.children
        if not children:
            continue
        has_entity_decorator = any(
            c.type == "decorator" and "@Entity" in _text(c, source) for c in children
        )
        for class_node in children:
            if class_node.type != "class_declaration":
                continue
            name = _child_field(class_node, "name")
            class_name = _text(name, source) if name else ""
            if not class_name:
                continue
            if has_entity_decorator or _extends_sequelize_model(class_node, source):
                yield class_name
    for node in _walk(root):
        if node.type == "call_expression" and _is_sequelize_define_call(node, source):
            first_arg = _first_string_arg(node, source)
            if first_arg:
                yield first_arg


def _extends_sequelize_model(class_node: Any, source: bytes) -> bool:
    heritage = _child_by_type(class_node, "class_heritage")
    if not heritage:
        return False
    txt = _text(heritage, source)
    return "Model" in txt


def _is_sequelize_define_call(call_node: Any, source: bytes) -> bool:
    func = _child_field(call_node, "function")
    if not func:
        return False
    txt = _text(func, source)
    return txt.endswith(".define") or txt == "define"


def _first_string_arg(call_node: Any, source: bytes) -> str | None:
    args = _child_field(call_node, "arguments")
    if not args:
        return None
    for child in args.children:
        if child.type in {"string", "template_string"}:
            raw = _text(child, source)
            return raw.strip("'\"`")
    return None


def _units_in_tree(
    root: Any,
    source: bytes,
    rel_path: str,
    entities: set[str],
) -> Iterator[Unit]:
    class_stack: list[str] = []

    def visit(node: Any) -> Iterator[Unit]:
        if node.type == "class_declaration":
            name = _child_field(node, "name")
            class_stack.append(_text(name, source) if name else "")
            for child in node.children:
                yield from visit(child)
            class_stack.pop()
            return
        if node.type in {
            "function_declaration",
            "method_definition",
            "arrow_function",
        }:
            ident = _function_ident(node, source) or "<anon>"
            resources = _collect_entities(node, source, entities)
            if resources:
                qualified = (
                    f"{class_stack[-1]}.{ident}" if class_stack and class_stack[-1] else ident
                )
                lineno = node.start_point[0] + 1
                yield Unit(
                    location=f"{rel_path}:{lineno}",
                    name=qualified,
                    resources=frozenset(resources),
                    language="typescript",
                )
            return
        for child in node.children:
            yield from visit(child)

    yield from visit(root)


def _function_ident(node: Any, source: bytes) -> str | None:
    name = _child_field(node, "name")
    if name:
        return _text(name, source)
    return None


def _collect_entities(node: Any, source: bytes, entities: set[str]) -> set[str]:
    found: set[str] = set()
    for child in _walk(node):
        if child.type == "identifier":
            txt = _text(child, source)
            if txt in entities:
                found.add(txt)
    return found


def _walk(node: Any) -> Iterator[Any]:
    yield node
    for child in node.children:
        yield from _walk(child)


def _child_field(node: Any, field_name: str) -> Any:
    return node.child_by_field_name(field_name)


def _child_by_type(node: Any, type_name: str) -> Any:
    for child in node.children:
        if child.type == type_name:
            return child
    return None
