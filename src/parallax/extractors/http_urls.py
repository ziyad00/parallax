"""HTTP URL extractor.

Resources are URL paths (host stripped, dynamic segments collapsed).
Each file emits **one Unit per distinct URL it references** with
``resources={url}``. This is what lets every file touching ``/foo/{id}``
land in the same cluster — even if those files reference completely
different supersets of other URLs. The trade-off versus a per-file
resource-bag model is that singleton clusters (a URL mentioned in
exactly one file) become meaningful: that's typically a frontend
calling an endpoint the backend doesn't expose, or vice versa.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator

from ..core import Unit
from .base import Extractor


_URL_RE = re.compile(
    r"""
    (?:
        # Absolute URL: https://host/path
        https?://[^\s"'`<>{}\\]+
        |
        # Path-only: "/v1/foo/bar" — at least 2 segments, no spaces/quotes.
        # The character class includes ``$`` so Dart string interpolation
        # (``/foo/$bar`` or ``/foo/${bar}``) is captured as one token rather
        # than split at the ``$`` boundary.
        /[a-zA-Z][\w./\-{}:$]*(?:/[\w./\-{}:$]+)+
    )
    """,
    re.VERBOSE,
)


DEFAULT_TEXT_EXTENSIONS = {
    ".py", ".pyi",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".dart",
    ".go", ".rs", ".java", ".kt", ".rb", ".php",
    ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".json", ".toml",
    ".tf", ".tfvars",
    ".md",
}

DEFAULT_IGNORE_DIRS = {
    "__pycache__",
    ".venv", "venv",
    ".git",
    "node_modules",
    "dist", "build", "target",
    ".next", ".nuxt",
}


class HttpUrlExtractor(Extractor):
    """Find files that mention the same HTTP URL paths."""

    name = "http-urls"

    def __init__(
        self,
        *,
        text_extensions: set[str] | None = None,
        ignore_dirs: set[str] | None = None,
        match_path_only: bool = True,
    ) -> None:
        self.text_extensions = text_extensions or DEFAULT_TEXT_EXTENSIONS
        self.ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS
        self.match_path_only = match_path_only

    def extract(self, root: Path) -> Iterable[Unit]:
        return list(self._scan(root))

    def _scan(self, root: Path) -> Iterator[Unit]:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in self.ignore_dirs for part in path.parts):
                continue
            if path.suffix not in self.text_extensions:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            # First occurrence of each normalized URL keeps its line
            # number so the location string is clickable in editors and
            # SARIF reporters.
            first_line: dict[str, int] = {}
            for match in _URL_RE.finditer(text):
                resource = self.normalize_url(match.group(0))
                if not resource or resource in first_line:
                    continue
                first_line[resource] = text.count("\n", 0, match.start()) + 1

            if not first_line:
                continue

            rel = path.relative_to(root).as_posix()
            language = _language_from_suffix(path.suffix)
            for url, line in first_line.items():
                yield Unit(
                    location=f"{rel}:{line}",
                    name=url,
                    resources=frozenset({url}),
                    language=language,
                )

    def normalize_url(self, raw: str) -> str:
        """Reduce a raw URL match to a stable path identifier.

        Strips scheme + host, drops query/fragment, collapses every kind
        of dynamic path segment to the canonical ``{id}`` placeholder, and
        removes any trailing slash. Override for stricter or looser
        matching.

        Dynamic-segment forms all collapse to ``{id}``:
        - Numeric: ``/123``
        - OpenAPI / FastAPI braces: ``/{user_id}``
        - Dart interpolation: ``/$userId``, ``/${userId}``

        This is what lets a FastAPI route ``/follow/requests/{user_id}``
        cluster with a Dart call site ``/follow/requests/$userId`` — they
        normalize to the same identifier even though the source code
        spelling diverges across languages.
        """
        path = raw
        if "://" in path:
            after_host = path.split("://", 1)[1]
            slash = after_host.find("/")
            path = after_host[slash:] if slash >= 0 else "/"
        for sep in "?#":
            if sep in path:
                path = path.split(sep, 1)[0]
        # Dart ``${name}`` first; do it before the bare-``$name`` form so
        # the closing brace is consumed atomically.
        path = re.sub(r"/\$\{[^}/]+\}", "/{id}", path)
        # Dart bare interpolation ``$name`` — must start with a letter or
        # underscore so we don't munch query-style ``$1`` (which is
        # already covered by the numeric rule below).
        path = re.sub(r"/\$[A-Za-z_]\w*", "/{id}", path)
        # OpenAPI / FastAPI braces ``{user_id}``.
        path = re.sub(r"/\{[^}/]+\}", "/{id}", path)
        # Numeric segments ``/123``.
        path = re.sub(r"/\d+", "/{id}", path)
        if path.endswith("/") and len(path) > 1:
            path = path[:-1]
        return path


_SUFFIX_TO_LANG = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".dart": "dart",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".rb": "ruby", ".php": "php",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
    ".tf": "terraform", ".tfvars": "terraform",
    ".md": "markdown",
}


def _language_from_suffix(suffix: str) -> str:
    return _SUFFIX_TO_LANG.get(suffix, "")
