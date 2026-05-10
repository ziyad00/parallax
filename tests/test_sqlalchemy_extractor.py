from pathlib import Path

from parallax.core import group_by_resource_set
from parallax.extractors import SqlAlchemyExtractor


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sqlalchemy_app"


def test_discovers_models_by_base_class_subclass():
    units = list(SqlAlchemyExtractor().extract(FIXTURE_ROOT))
    # Three model classes (User/Order/LineItem) are referenced in
    # service_a + service_b. We expect at least 3 units (one per
    # function with model references).
    assert len(units) >= 3


def test_clusters_two_services_joining_same_tables():
    units = list(SqlAlchemyExtractor().extract(FIXTURE_ROOT))
    clusters = group_by_resource_set(units, min_resources=2)
    # The two services touching User + Order + LineItem land in one
    # cluster with two members.
    triple_clusters = [c for c in clusters if c.resources == frozenset({"User", "Order", "LineItem"})]
    assert len(triple_clusters) == 1
    members = {u.location.split(":")[0] for u in triple_clusters[0].units}
    assert members == {"service_a.py", "service_b.py"}


def test_lookup_unrelated_does_not_cluster_with_the_pair():
    units = list(SqlAlchemyExtractor().extract(FIXTURE_ROOT))
    clusters = group_by_resource_set(units, min_resources=2)
    # service_b.lookup_unrelated only references User — not in the
    # 3-resource cluster.
    triple = next(
        c for c in clusters
        if c.resources == frozenset({"User", "Order", "LineItem"})
    )
    names = {u.name for u in triple.units}
    assert "lookup_unrelated" not in names
