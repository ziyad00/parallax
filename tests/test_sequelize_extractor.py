from pathlib import Path

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_typescript")

from parallax.core import group_by_resource_set
from parallax.extractors import SequelizeExtractor


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sequelize_app"


def test_discovers_typeorm_entities():
    units = list(SequelizeExtractor().extract(FIXTURE_ROOT))
    assert units, "expected at least one unit"
    resources = set().union(*(u.resources for u in units))
    assert {"User", "Order", "LineItem"} <= resources


def test_clusters_two_typescript_services_touching_same_entities():
    units = list(SequelizeExtractor().extract(FIXTURE_ROOT))
    clusters = group_by_resource_set(units, min_resources=2)
    matching = [
        c
        for c in clusters
        if c.resources == frozenset({"User", "Order", "LineItem"})
    ]
    assert matching
    files = {u.location.split(":", 1)[0] for u in matching[0].units}
    assert "service_a.ts" in files
    assert "service_b.ts" in files
