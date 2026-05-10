"""``.parallax.toml`` loader."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore


CONFIG_FILENAME = ".parallax.toml"


@dataclass(frozen=True)
class IgnoreRule:
    """Suppresses clusters whose resource set equals ``resources``."""

    resources: frozenset[str]
    extractor: str | None = None
    reason: str = ""


@dataclass
class Config:
    min_resources: int = 2
    min_cluster_size: int = 2
    max_cluster_size: int | None = None
    ignore: list[IgnoreRule] = field(default_factory=list)

    def matches_ignore(self, resources: frozenset[str]) -> IgnoreRule | None:
        for rule in self.ignore:
            if rule.resources == resources:
                return rule
        return None


def load_config(path: Path | None = None, *, search_root: Path | None = None) -> Config:
    """Load config from ``path`` or auto-discover ``.parallax.toml`` under
    ``search_root`` (defaults to cwd). Returns defaults when no file is found."""
    config_path = _resolve_config_path(path, search_root)
    if config_path is None:
        return Config()
    return _parse(config_path)


def _resolve_config_path(path: Path | None, search_root: Path | None) -> Path | None:
    if path is not None:
        if not path.exists():
            raise FileNotFoundError(f"config not found: {path}")
        return path
    root = search_root or Path.cwd()
    candidate = root / CONFIG_FILENAME
    if candidate.exists():
        return candidate
    return None


def _parse(config_path: Path) -> Config:
    with config_path.open("rb") as f:
        data = tomllib.load(f)

    scan = data.get("scan", {})
    ci = data.get("ci", {})
    ignore_blocks = data.get("ignore", []) or []

    ignore_rules: list[IgnoreRule] = []
    for block in ignore_blocks:
        resources = block.get("resources")
        if not resources:
            raise ValueError(
                f"ignore rule in {config_path} missing required 'resources' field"
            )
        ignore_rules.append(
            IgnoreRule(
                resources=frozenset(resources),
                extractor=block.get("extractor"),
                reason=block.get("reason", ""),
            )
        )

    return Config(
        min_resources=int(scan.get("min_resources", 2)),
        min_cluster_size=int(scan.get("min_cluster_size", 2)),
        max_cluster_size=ci.get("max_cluster_size"),
        ignore=ignore_rules,
    )
