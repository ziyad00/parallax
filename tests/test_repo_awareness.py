from pathlib import Path

from parallax.core import group_by_resource_set
from parallax.extractors import SqlAlchemyExtractor


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "repo_app"


def test_follow_repos_clusters_inline_query_with_repo_caller():
    units = list(SqlAlchemyExtractor(follow_repos=True).extract(FIXTURE_ROOT))
    clusters = group_by_resource_set(units, min_resources=2)
    follow_user = [c for c in clusters if c.resources == frozenset({"Follow", "User"})]
    assert len(follow_user) == 1
    names = {u.name for u in follow_user[0].units}
    assert "list_user_followers" in names
    assert "list_user_followers_via_repo" in names


def test_without_follow_repos_caller_is_invisible():
    units = list(SqlAlchemyExtractor(follow_repos=False).extract(FIXTURE_ROOT))
    by_name = {u.name: u for u in units}
    assert "list_user_followers_via_repo" not in by_name


def test_repo_class_suffix_is_configurable():
    units = list(
        SqlAlchemyExtractor(
            follow_repos=True, repo_class_suffix="NonExistent"
        ).extract(FIXTURE_ROOT)
    )
    by_name = {u.name: u for u in units}
    assert "list_user_followers_via_repo" not in by_name
