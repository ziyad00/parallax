"""FastAPI routes extractor.

Resolves the effective URL of every ``@router.METHOD("/path")``
decorator in the tree, accounting for both prefix sources:

1. Router-level: ``router = APIRouter(prefix="/follow")``.
2. App-level: ``app.include_router(follow_router, prefix="/follow")``,
   resolved across files via the import that brought the router into
   the file calling ``include_router``.

Emits one :class:`~parallax.core.Unit` per resolved route.

Why this exists separately from ``http-urls``: FastAPI routers spell
the prefix once and reuse it across many decorators, so the literal
string in the decorator (``"/bar"``) is often too short to be picked
up by a generic URL scanner — and the prefix may live in a completely
different file from the route declarations. A text-only extractor
can't reconstruct the full URL.

The output resource is the path only (no HTTP method) so a route here
clusters with a Dart caller emitted by ``http-urls``. The HTTP method
is preserved in ``Unit.extra["method"]`` for downstream consumers that
want stricter checks.

Path-param syntaxes collapse to ``{id}``, matching the http-urls
extractor's normalization so cross-language clusters land on the same
canonical resource.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable, Iterator, Optional

from ..core import Unit
from .base import Extractor


DEFAULT_IGNORE_DIRS = {
    "__pycache__",
    ".venv", "venv",
    ".git",
    "node_modules",
    "dist", "build", "target",
    ".next", ".nuxt",
    "migrations",  # alembic / django leftovers
    "tests",       # test routers inflate signal and aren't part of the contract
}


_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


class FastApiRoutesExtractor(Extractor):
    """Emit one Unit per ``@router.METHOD("/path")`` declared in the tree."""

    name = "fastapi-routes"

    def __init__(self, *, ignore_dirs: set[str] | None = None) -> None:
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS

    def extract(self, root: Path) -> Iterable[Unit]:
        return list(self._scan(root))

    def _walk(self, root: Path) -> Iterator[Path]:
        for p in root.rglob("*.py"):
            if any(part in self.ignore_dirs for part in p.parts):
                continue
            yield p

    def _scan(self, root: Path) -> Iterator[Unit]:
        # Pass 1: walk the whole tree to collect prefixes attached at
        # include_router(...) sites. Each entry is keyed by the imported
        # router's (module_file_suffix, var_name) so pass 2 can match it
        # against locally declared routers.
        include_prefixes = _collect_include_router_prefixes(list(self._walk(root)))

        # Pass 2: per-file route extraction.
        for py in self._walk(root):
            try:
                source = py.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue

            local_prefixes = _collect_router_prefixes(tree)
            if not local_prefixes:
                continue

            file_suffix = py.relative_to(root).as_posix()
            # Combine the router-level prefix with any include_router
            # prefix that targets this specific (file, var).
            prefixes: dict[str, str] = {}
            for var, local in local_prefixes.items():
                include = _lookup_include_prefix(
                    include_prefixes, file_suffix=file_suffix, var_name=var
                )
                prefixes[var] = _join_path(include, local)

            rel = file_suffix
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for dec in node.decorator_list:
                    route = _decorator_to_route(dec, prefixes)
                    if route is None:
                        continue
                    method, path = route
                    yield Unit(
                        location=f"{rel}:{dec.lineno}",
                        name=node.name,
                        resources=frozenset({_normalize_path(path)}),
                        language="python",
                        extra={"method": method.upper(), "raw_path": path},
                    )


def _collect_router_prefixes(tree: ast.AST) -> dict[str, str]:
    """Return a map of router variable name → prefix string.

    Handles the common single-file pattern:

        router = APIRouter(prefix="/follow")

    Also recognises ``app = FastAPI()`` so top-level ``@app.get("/")``
    routes don't get dropped.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        callee = node.value.func
        callee_name: Optional[str] = None
        if isinstance(callee, ast.Name):
            callee_name = callee.id
        elif isinstance(callee, ast.Attribute):
            callee_name = callee.attr
        if callee_name not in {"APIRouter", "FastAPI"}:
            continue

        prefix = ""
        for kw in node.value.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    prefix = kw.value.value
                    break

        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = prefix
    return out


def _collect_include_router_prefixes(
    py_files: list[Path],
) -> list[tuple[str, str, str]]:
    """Return a list of ``(module_suffix, var_name, prefix)`` tuples.

    Walks every file looking for two patterns:

        from .routers.follow import router as follow_router
        app.include_router(follow_router, prefix="/follow")

    For each ``include_router(X, prefix=Y)`` call we resolve ``X`` back
    to its imported source via the file's import table and yield an
    entry that pass 2 can match against a router declared elsewhere.

    ``module_suffix`` is the imported module converted to a path suffix
    (``routers.follow`` → ``routers/follow.py``). Pass 2 matches it
    against the actual file path with ``endswith`` so the package root
    doesn't have to be known precisely.
    """
    out: list[tuple[str, str, str]] = []
    for py in py_files:
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue

        # alias → (module_suffix, original_var)
        imports: dict[str, tuple[str, str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = (node.module or "").replace(".", "/")
                if not module:
                    continue
                module_suffix = module + ".py"
                for n in node.names:
                    alias = n.asname or n.name
                    imports[alias] = (module_suffix, n.name)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "include_router":
                continue
            if not node.args or not isinstance(node.args[0], ast.Name):
                continue
            alias = node.args[0].id
            prefix = ""
            for kw in node.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    if isinstance(kw.value.value, str):
                        prefix = kw.value.value
                        break
            if not prefix:
                continue  # No prefix added at include time — nothing to record.
            if alias in imports:
                module_suffix, original_var = imports[alias]
                out.append((module_suffix, original_var, prefix))
            else:
                # Locally declared router in the same file as the
                # include_router call — match by the file itself.
                out.append((py.name, alias, prefix))
    return out


def _lookup_include_prefix(
    entries: list[tuple[str, str, str]],
    *,
    file_suffix: str,
    var_name: str,
) -> str:
    """Find the prefix attached to ``(file_suffix, var_name)`` via include_router."""
    for module_suffix, original_var, prefix in entries:
        if original_var != var_name:
            continue
        if file_suffix.endswith(module_suffix):
            return prefix
    return ""


def _decorator_to_route(
    dec: ast.expr, prefixes: dict[str, str]
) -> Optional[tuple[str, str]]:
    """Return ``(method, full_path)`` if ``dec`` is ``@router.METHOD("...")``.

    The literal path string is the first positional arg (or the ``path=``
    kwarg). Decorators with non-literal paths (f-strings, variables) are
    skipped — they're rare in FastAPI and not worth the complexity here.
    """
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
        return None
    method = func.attr.lower()
    if method not in _HTTP_METHODS:
        return None
    router_name = func.value.id
    if router_name not in prefixes:
        return None

    raw_path: Optional[str] = None
    if dec.args:
        first = dec.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            raw_path = first.value
    if raw_path is None:
        for kw in dec.keywords:
            if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                if isinstance(kw.value.value, str):
                    raw_path = kw.value.value
                    break
    if raw_path is None:
        return None

    prefix = prefixes[router_name]
    full = _join_path(prefix, raw_path)
    return method, full


def _join_path(prefix: str, path: str) -> str:
    """Concatenate prefix + path, collapsing any double slash at the seam."""
    if not prefix:
        return path or "/"
    if not path:
        return prefix
    if prefix.endswith("/") and path.startswith("/"):
        return prefix[:-1] + path
    if not prefix.endswith("/") and not path.startswith("/"):
        return f"{prefix}/{path}"
    return prefix + path


def _normalize_path(path: str) -> str:
    """Mirror ``HttpUrlExtractor.normalize_url`` for the path portion.

    FastAPI routes never carry scheme/host, so the heavy lifting here is
    just collapsing dynamic segments to ``{id}``.
    """
    path = re.sub(r"/\{[^}/]+\}", "/{id}", path)
    path = re.sub(r"/\d+", "/{id}", path)
    if path.endswith("/") and len(path) > 1:
        path = path[:-1]
    return path
