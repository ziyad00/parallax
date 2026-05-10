from parallax.core import Unit, group_by_resource_set


def make_unit(name: str, resources: set[str]) -> Unit:
    return Unit(location=f"x/{name}.py:1", name=name, resources=frozenset(resources))


def test_groups_units_with_identical_resource_set():
    a = make_unit("a", {"User", "Order"})
    b = make_unit("b", {"User", "Order"})
    c = make_unit("c", {"User"})

    clusters = group_by_resource_set([a, b, c])

    # Single cluster with a + b; c is alone and filtered out.
    assert len(clusters) == 1
    assert clusters[0].size == 2
    assert {u.name for u in clusters[0].units} == {"a", "b"}


def test_min_resources_filters_generic_overlaps():
    a = make_unit("a", {"User"})
    b = make_unit("b", {"User"})
    clusters = group_by_resource_set([a, b], min_resources=2)
    assert clusters == []


def test_min_cluster_size_filters_singletons():
    a = make_unit("a", {"User", "Order"})
    clusters = group_by_resource_set([a], min_cluster_size=2)
    assert clusters == []


def test_clusters_sorted_by_size_then_resource_count():
    big_a = make_unit("big_a", {"X", "Y"})
    big_b = make_unit("big_b", {"X", "Y"})
    big_c = make_unit("big_c", {"X", "Y"})
    deep_a = make_unit("deep_a", {"P", "Q", "R"})
    deep_b = make_unit("deep_b", {"P", "Q", "R"})

    clusters = group_by_resource_set([big_a, big_b, big_c, deep_a, deep_b])

    # Three-member cluster wins on size first.
    assert clusters[0].size == 3
    # Two-member cluster comes next; it has more resources than the
    # other 2-member clusters (none here, so this just verifies order).
    assert clusters[1].size == 2
    assert sorted(clusters[1].resources) == ["P", "Q", "R"]
