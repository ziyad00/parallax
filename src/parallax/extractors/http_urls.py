"""HTTP URL extractor.

Resources are URL paths (host stripped, dynamic segments collapsed).
Each text file emits one :class:`~parallax.core.Unit` covering the
URLs it references.
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
        # Path-only: "/v1/foo/bar" — at least 2 segments, no spaces/quotes
        /[a-zA-Z][\w./\-{}:]*(?:/[\w./\-{}:]+)+
    )
    """,
    re.VERBOSE,
)


DEFAULT_TEXT_EXTENSIONS = {
    ".py", ".pyi",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
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

            urls = set()
            for match in _URL_RE.finditer(text):
                resource = self.normalize_url(match.group(0))
                if resource:
                    urls.add(resource)

            if urls:
                rel = path.relative_to(root).as_posix()
                yield Unit(
                    location=rel,
                    name=path.name,
                    resources=frozenset(urls),
                    language=_language_from_suffix(path.suffix),
                )

    def normalize_url(self, raw: str) -> str:
        """Reduce a raw URL match to a stable path identifier.

        Strips scheme + host, drops query/fragment, replaces numeric
        path segments with ``{id}``, and removes any trailing slash.
        Override for stricter or looser matching.
        """
        path = raw
        if "://" in path:
            after_host = path.split("://", 1)[1]
            slash = after_host.find("/")
            path = after_host[slash:] if slash >= 0 else "/"
        for sep in "?#":
            if sep in path:
                path = path.split(sep, 1)[0]
        path = re.sub(r"/\d+", "/{id}", path)
        if path.endswith("/") and len(path) > 1:
            path = path[:-1]
        return path


_SUFFIX_TO_LANG = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
    ".rb": "ruby", ".php": "php",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json", ".toml": "toml",
    ".tf": "terraform", ".tfvars": "terraform",
    ".md": "markdown",
}


def _language_from_suffix(suffix: str) -> str:
    return _SUFFIX_TO_LANG.get(suffix, "")
