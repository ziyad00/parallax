from parallax.core import Cluster, Unit, group_by_resource_set


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


def test_clusters_sorted_by_score_descending():
    """v0.2: clusters sort by interestingness score (rarity x size x
    breadth x cross-file factor), not raw size."""
    # 3-member cluster of {X, Y} where X and Y appear in every unit
    # (no rarity advantage).
    big_a = make_unit("big_a", {"X", "Y"})
    big_b = make_unit("big_b", {"X", "Y"})
    big_c = make_unit("big_c", {"X", "Y"})
    # 2-member cluster with 3 distinct resources — broader cluster
    # AND its tables don't appear elsewhere → higher rarity → higher
    # score, even though size is smaller.
    deep_a = make_unit("deep_a", {"P", "Q", "R"})
    deep_b = make_unit("deep_b", {"P", "Q", "R"})

    clusters = group_by_resource_set([big_a, big_b, big_c, deep_a, deep_b])

    # The 3-resource cluster wins on score because rarity x breadth
    # x size beats raw size alone when X+Y are present everywhere.
    assert sorted(clusters[0].resources) == ["P", "Q", "R"]
    assert clusters[0].score > clusters[1].score


def test_score_buries_hub_table_clusters():
    """A 'hub table' (touched by every unit) drags cluster scores down,
    so a small specific cluster beats a big generic one."""
    # 5 units that all touch User. 4 of them are in the hub-cluster
    # User+Place. 1 is in a small-but-rare cluster Order+LineItem.
    hub = [
        make_unit(f"h{i}", {"User", "Place"}) for i in range(4)
    ]
    rare = [
        make_unit("o1", {"Order", "LineItem"}),
        make_unit("o2", {"Order", "LineItem"}),
    ]
    clusters = group_by_resource_set(hub + rare)
    # Hub cluster has 4 members; rare has 2. Score should still rank
    # the rare one higher (or close) because User/Place are touched
    # everywhere.
    rare_cluster = next(c for c in clusters if "Order" in c.resources)
    hub_cluster = next(c for c in clusters if "User" in c.resources)
    assert rare_cluster.score > hub_cluster.score


def test_cross_file_filter_drops_same_file_clusters():
    """--cross-file-only should drop clusters confined to one file."""
    same_file = [
        Unit(location="x.py:1", name="a", resources=frozenset({"P", "Q", "R"})),
        Unit(location="x.py:5", name="b", resources=frozenset({"P", "Q", "R"})),
    ]
    cross_file = [
        Unit(location="a.py:1", name="x", resources=frozenset({"M", "N", "O"})),
        Unit(location="b.py:1", name="y", resources=frozenset({"M", "N", "O"})),
    ]
    clusters = group_by_resource_set(
        same_file + cross_file, cross_file_only=True
    )
    assert len(clusters) == 1
    assert sorted(clusters[0].resources) == ["M", "N", "O"]


def test_cluster_is_cross_file_property():
    same = Cluster(
        resources=frozenset({"X"}),
        units=[
            Unit(location="a.py:1", name="x", resources=frozenset({"X"})),
            Unit(location="a.py:5", name="y", resources=frozenset({"X"})),
        ],
    )
    crossing = Cluster(
        resources=frozenset({"X"}),
        units=[
            Unit(location="a.py:1", name="x", resources=frozenset({"X"})),
            Unit(location="b.py:5", name="y", resources=frozenset({"X"})),
        ],
    )
    assert same.is_cross_file is False
    assert crossing.is_cross_file is True
