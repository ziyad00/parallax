"""Language-agnostic HTTP URL extractor.

Treats each source file as a unit (no language parsing required) and
its resource set as the URL paths it references. Works on Python, JS,
TS, Go, Java, Ruby, shell, YAML, JSON, OpenAPI specs, Terraform, etc.

Two files calling the same external HTTP endpoint cluster together,
regardless of how the call is written (axios, requests, curl, fetch,
http.Get, ...). Surfaces patterns like "five different services all
talking to the same Stripe endpoint with their own retry policies."

The path is what's compared, not the host — so ``GET /v1/charges``
clusters across hosts. Strip the host or override
:meth:`normalize_url` if you want stricter matching.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator

from ..core import Unit
from .base import Extractor


# Reasonable default — captures absolute and relative URL-like strings.
# Tuned to skip false positives (file paths, Python module paths) by
# requiring an http(s):// prefix or a leading slash followed by a
# segment that doesn't look like a Windows path.
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


# File extensions we read as plain text. Adding more is cheap.
DEFAULT_TEXT_EXTENSIONS = {
    ".py", ".pyi",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".rb", ".php",
    ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".json", ".toml",
    ".tf", ".tfvars",
    ".md",  # docs / runbooks often hardcode URLs
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
        """Reduce a raw URL match to the resource identifier we cluster on.

        Default: keep only the path component, normalize trailing slash,
        and replace path parameters (e.g. ``/users/123``) with ``{id}``
        so different concrete invocations of the same endpoint match.
        Override for stricter or looser matching.
        """
        path = raw
        # Strip scheme + host to leave the path
        if "://" in path:
            after_host = path.split("://", 1)[1]
            slash = after_host.find("/")
            path = after_host[slash:] if slash >= 0 else "/"
        # Strip query string + fragment
        for sep in "?#":
            if sep in path:
                path = path.split(sep, 1)[0]
        # Replace numeric path segments with {id} so /v1/foo/123 == /v1/foo/456
        path = re.sub(r"/\d+", "/{id}", path)
        # Normalise trailing slash
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
