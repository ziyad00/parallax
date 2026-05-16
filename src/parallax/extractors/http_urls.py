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


# A URL that ends in one of these suffixes is almost certainly an import
# path or relative file reference (e.g.
# ``/scr/feature/profile/profile_viewmodel.dart``) and not a real HTTP
# route. Filtering them out at extraction time keeps the cluster output
# focused on cross-repo API drift.
_SOURCE_FILE_SUFFIXES = (
    ".dart", ".py", ".pyi",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".rb", ".php",
    ".html", ".css", ".scss",
)


# Per-language single-line comment markers. The match's containing line
# is inspected: if the first non-whitespace characters are one of these,
# the match is discarded. This kills false positives like
# ``// see /update/delete docs`` or ``# example: /foo/bar`` without
# affecting real string literals on uncommented code lines.
_COMMENT_LINE_PREFIXES = ("#", "//", "/*", "*")


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
                if _is_in_comment_line(text, match.start()):
                    continue
                resource = self.normalize_url(match.group(0))
                if not resource or _looks_like_source_file_path(resource):
                    continue
                if resource in first_line:
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


def _is_in_comment_line(text: str, match_start: int) -> bool:
    """True if the match is inside a comment — either a whole-line
    comment or a trailing comment on a code line.

    Whole-line case: the line's first non-whitespace token is a comment
    marker.

    Trailing-line case: a comment marker (``//`` or ``#``) appears
    between the line start and ``match_start``, outside a string
    literal. Quote-pair counting is approximate but good enough for
    the common ``final foo = "thing"; // /old/route`` shape.
    """
    line_start = text.rfind("\n", 0, match_start) + 1
    line_end = text.find("\n", match_start)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end]
    if line.lstrip().startswith(_COMMENT_LINE_PREFIXES):
        return True
    prefix = text[line_start:match_start]
    return _prefix_has_unstrung_comment(prefix)


def _prefix_has_unstrung_comment(prefix: str) -> bool:
    """True if ``//`` or ``#`` appears in ``prefix`` outside any string
    literal. Strings open and close on ``'`` and ``"`` (backslash-
    escaped pairs ignored). Triple-quoted strings, raw strings, and
    multi-line strings aren't handled — they'd need a real tokenizer
    and are rare in URL-bearing source."""
    in_str: str | None = None
    i = 0
    while i < len(prefix):
        ch = prefix[i]
        if in_str:
            if ch == "\\" and i + 1 < len(prefix):
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ("'", '"'):
                in_str = ch
            elif ch == "/" and i + 1 < len(prefix) and prefix[i + 1] == "/":
                return True
            elif ch == "#":
                return True
        i += 1
    return False


def _looks_like_source_file_path(resource: str) -> bool:
    """Reject extracted paths that are import/file references rather
    than HTTP routes — anything ending in a known source-file suffix
    falls into this bucket."""
    return resource.endswith(_SOURCE_FILE_SUFFIXES)
