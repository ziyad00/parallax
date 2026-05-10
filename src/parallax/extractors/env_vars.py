"""Environment-variable extractor.

Resources are environment variable names read by the file. Patterns
cover Python (``os.environ`` / ``os.getenv``), JS/TS (``process.env``
/ ``import.meta.env``), Go (``os.Getenv`` / ``os.LookupEnv``), Rust
(``env::var``), and shell (``$NAME`` / ``${NAME}``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator

from ..core import Unit
from .base import Extractor
from .http_urls import (
    DEFAULT_IGNORE_DIRS as _SHARED_IGNORE,
    DEFAULT_TEXT_EXTENSIONS as _SHARED_TEXT_EXT,
    _language_from_suffix,
)


_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"""os\.environ(?:\.get)?\s*[\(\[]\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    re.compile(r"""os\.getenv\s*\(\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    re.compile(r"""process\.env\.([A-Z_][A-Z0-9_]*)\b"""),
    re.compile(r"""process\.env\[\s*["']([A-Z_][A-Z0-9_]*)["']\s*\]"""),
    re.compile(r"""import\.meta\.env\.([A-Z_][A-Z0-9_]*)\b"""),
    re.compile(r"""os\.(?:Getenv|LookupEnv)\s*\(\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    re.compile(r"""env::var\s*\(\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    # Restricted to ALL_CAPS names so $1, $#, $@ are skipped.
    re.compile(r"""\$\{([A-Z_][A-Z0-9_]*)\}"""),
    re.compile(r"""\$([A-Z_][A-Z0-9_]*)\b"""),
]


class EnvVarsExtractor(Extractor):
    """Find files that read the same environment variables."""

    name = "env-vars"

    def __init__(
        self,
        *,
        text_extensions: set[str] | None = None,
        ignore_dirs: set[str] | None = None,
    ) -> None:
        self.text_extensions = text_extensions or _SHARED_TEXT_EXT
        self.ignore_dirs = ignore_dirs or _SHARED_IGNORE

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

            envs: set[str] = set()
            for pat in _PATTERNS:
                for m in pat.finditer(text):
                    envs.add(m.group(1))

            if envs:
                rel = path.relative_to(root).as_posix()
                yield Unit(
                    location=rel,
                    name=path.name,
                    resources=frozenset(envs),
                    language=_language_from_suffix(path.suffix),
                )
