"""Tests for config loading + CI behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from parallax.cli import main as cli_main
from parallax.config import IgnoreRule, load_config


def write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_load_default_when_no_config(tmp_path):
    cfg = load_config(search_root=tmp_path)
    assert cfg.min_resources == 2
    assert cfg.min_cluster_size == 2
    assert cfg.max_cluster_size is None
    assert cfg.ignore == []


def test_load_full_config(tmp_path):
    write(
        tmp_path / ".parallax.toml",
        """
        [scan]
        min_resources = 3
        min_cluster_size = 4

        [ci]
        max_cluster_size = 5

        [[ignore]]
        resources = ["User", "Place"]
        reason = "Generic"

        [[ignore]]
        resources = ["session"]
        extractor = "redis-keys"
        """,
    )
    cfg = load_config(search_root=tmp_path)
    assert cfg.min_resources == 3
    assert cfg.min_cluster_size == 4
    assert cfg.max_cluster_size == 5
    assert len(cfg.ignore) == 2
    assert cfg.ignore[0].resources == frozenset({"User", "Place"})
    assert cfg.ignore[0].reason == "Generic"
    assert cfg.ignore[1].extractor == "redis-keys"


def test_matches_ignore_rule():
    rules = [IgnoreRule(resources=frozenset({"X", "Y"}))]
    from parallax.config import Config

    cfg = Config(ignore=rules)
    assert cfg.matches_ignore(frozenset({"X", "Y"})) is not None
    assert cfg.matches_ignore(frozenset({"X"})) is None


def test_explicit_config_path_missing_raises(tmp_path):
    missing = tmp_path / "nope.toml"
    with pytest.raises(FileNotFoundError):
        load_config(missing)


def test_ci_mode_passes_when_cluster_size_below_threshold(tmp_path, capsys):
    """One 2-member cluster, max_cluster_size=3 -> exit 0 in CI mode."""
    fixture = Path(__file__).parent / "fixtures" / "sqlalchemy_app"
    write(
        tmp_path / ".parallax.toml",
        """
        [ci]
        max_cluster_size = 4
        """,
    )
    # Run from tmp_path so the config is auto-discovered.
    import os

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        rc = cli_main(["scan", str(fixture), "-e", "sqlalchemy", "--ci"])
    finally:
        os.chdir(cwd)
    assert rc == 0  # 2-member cluster < threshold


def test_ignore_rule_suppresses_cluster(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "sqlalchemy_app"
    # Suppress the only cluster the fixture produces.
    write(
        tmp_path / ".parallax.toml",
        """
        [[ignore]]
        resources = ["User", "Order", "LineItem"]
        reason = "Test ignore"
        """,
    )
    import os

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        rc = cli_main(["scan", str(fixture), "-e", "sqlalchemy"])
    finally:
        os.chdir(cwd)
    out = capsys.readouterr().out
    assert rc == 0  # Cluster suppressed, no findings.
    assert "1 cluster(s) suppressed by ignore rules" in out


def test_default_mode_fails_on_any_cluster(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "sqlalchemy_app"
    rc = cli_main(["scan", str(fixture), "-e", "sqlalchemy"])
    assert rc == 1
