"""Environment-variable extractor — language-agnostic.

For each text source file, the unit's resource set is the set of
environment variables the file reads. Catches files reading the same
configuration values from different code, regardless of language.

Picks up patterns like:

- Python: ``os.environ['X']``, ``os.environ.get('X')``, ``os.getenv('X')``
- JS / TS: ``process.env.X``, ``process.env['X']``, ``import.meta.env.X``
- Go: ``os.Getenv("X")``, ``os.LookupEnv("X")``
- Rust: ``std::env::var("X")``
- Shell: ``$X``, ``${X}``, ``$ENV{X}``
- Docker / compose / k8s: ``${X}`` placeholders
- Terraform: ``var.X``? — out of scope here, see a future TF extractor

Two services reading the same set of env vars are likely doing related
work (one of them duplicating the other's wiring). Surfaces config
sprawl, missing centralisation of secrets / endpoints / feature flags.
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


# Patterns are ordered most-specific first to avoid false positives.
_PATTERNS: list[re.Pattern[str]] = [
    # Python: os.environ["FOO"] / os.environ.get("FOO") / os.getenv("FOO")
    re.compile(r"""os\.environ(?:\.get)?\s*[\(\[]\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    re.compile(r"""os\.getenv\s*\(\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    # JS / TS: process.env.FOO / process.env["FOO"] / import.meta.env.FOO
    re.compile(r"""process\.env\.([A-Z_][A-Z0-9_]*)\b"""),
    re.compile(r"""process\.env\[\s*["']([A-Z_][A-Z0-9_]*)["']\s*\]"""),
    re.compile(r"""import\.meta\.env\.([A-Z_][A-Z0-9_]*)\b"""),
    # Go: os.Getenv("FOO") / os.LookupEnv("FOO")
    re.compile(r"""os\.(?:Getenv|LookupEnv)\s*\(\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    # Rust: std::env::var("FOO")
    re.compile(r"""env::var\s*\(\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    # Shell-style ${FOO} or $FOO — only ALL_CAPS to skip $1, $#, etc.
    re.compile(r"""\$\{([A-Z_][A-Z0-9_]*)\}"""),
    re.compile(r"""\$([A-Z_][A-Z0-9_]*)\b"""),
    # Compose / k8s: env: - name: FOO  (YAML structural references)
    # Skipped here; tracked separately if there's demand.
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
