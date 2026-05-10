from pathlib import Path

from parallax.core import group_by_resource_set
from parallax.extractors import DjangoExtractor


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "django_app"


def test_discovers_django_models_across_apps():
    units = list(DjangoExtractor().extract(FIXTURE_ROOT))
    assert len(units) >= 3


def test_clusters_two_views_referencing_same_models():
    units = list(DjangoExtractor().extract(FIXTURE_ROOT))
    clusters = group_by_resource_set(units, min_resources=2)
    triple = [
        c for c in clusters
        if c.resources == frozenset({"Profile", "Subscription", "Invoice"})
    ]
    assert len(triple) == 1
    assert {u.name for u in triple[0].units} == {"user_dashboard", "user_summary"}


def test_unrelated_lookup_does_not_cluster():
    units = list(DjangoExtractor().extract(FIXTURE_ROOT))
    clusters = group_by_resource_set(units, min_resources=2)
    triple = next(
        c for c in clusters
        if c.resources == frozenset({"Profile", "Subscription", "Invoice"})
    )
    assert "unrelated_lookup" not in {u.name for u in triple.units}
