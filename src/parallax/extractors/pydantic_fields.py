"""Pydantic / dataclass field extractor.

Walks Python source for ``class X(BaseModel):`` (and ``@dataclass``)
declarations AND inline dict literals passed to WebSocket-style
broadcast helpers, and emits one :class:`~parallax.core.Unit` per
declared / sent field. Resource is the field name canonicalised to
snake_case so ``isFollowed`` (Dart) and ``is_followed`` (Python)
cluster together.

Sources covered:

1. ``class X(BaseModel):`` — Pydantic schemas
2. ``@dataclass`` — Python dataclasses
3. Plain classes whose name ends in ``Response`` / ``Schema`` /
   ``Model`` / ``Out`` / ``DTO`` / ``Payload`` — heuristic for
   wire-shape classes that don't inherit Pydantic
4. **Inline dict literals** passed positionally to broadcast helpers
   (``broadcast_to_user``, ``send_json``, ``send_realtime_update``,
   ``broadcast_event``). These are real-time payload schemas that
   never become Pydantic classes but the frontend still reads them.

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
from ._field_canon import canonicalize_field
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


# Function names whose first dict-literal argument is treated as a
# real-time payload shape. These cover the broadcast helpers in
# circles-be (``broadcast_to_user``, ``send_json``,
# ``send_realtime_update``, ``broadcast_event``). Override via the
# extractor constructor.
BROADCAST_FUNCTION_NAMES = (
    "broadcast_to_user",
    "broadcast_event",
    "broadcast_message",
    "send_realtime_update",
    "send_json",
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
        broadcast_function_names: tuple[str, ...] = BROADCAST_FUNCTION_NAMES,
    ) -> None:
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        self.response_name_hints = response_name_hints
        self.broadcast_function_names = tuple(broadcast_function_names)

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
                if isinstance(node, ast.ClassDef) and self._is_response_shape(node):
                    for item in node.body:
                        field = _field_name(item)
                        if not field:
                            continue
                        canon = canonicalize_field(field)
                        yield Unit(
                            location=f"{rel}:{item.lineno}",
                            name=f"{node.name}.{field}",
                            resources=frozenset({canon}),
                            language="python",
                            extra={
                                "class": node.name,
                                "field": field,
                                "raw_field": field,
                            },
                        )
                elif isinstance(node, ast.Call):
                    yield from self._inline_dict_units(node, rel)

    def _inline_dict_units(self, call: ast.Call, rel: str) -> Iterator[Unit]:
        """Emit Units for the keys of a dict literal passed positionally
        to a known broadcast helper.

        Catches the ``broadcast_to_user(to, {"type": ..., "from_user":
        ..., ...})`` pattern where the wire shape lives inline rather
        than in a Pydantic class. Nested dicts are NOT recursed — the
        top-level keys are what the frontend reads.
        """
        callee = call.func
        if isinstance(callee, ast.Attribute):
            fn_name = callee.attr
        elif isinstance(callee, ast.Name):
            fn_name = callee.id
        else:
            return
        if fn_name not in self.broadcast_function_names:
            return

        # Scan positional args for the first dict literal.
        for arg in call.args:
            if not isinstance(arg, ast.Dict):
                continue
            for key in arg.keys:
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                field = key.value
                canon = canonicalize_field(field)
                yield Unit(
                    location=f"{rel}:{call.lineno}",
                    name=f"{fn_name}.{field}",
                    resources=frozenset({canon}),
                    language="python",
                    extra={
                        "broadcast": fn_name,
                        "field": field,
                        "raw_field": field,
                    },
                )
            return  # First dict only

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
