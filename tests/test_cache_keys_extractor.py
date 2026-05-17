"""Smoke tests for the cache-keys extractor."""

from __future__ import annotations

from pathlib import Path

from parallax.core import group_by_resource_set
from parallax.extractors import CacheKeysExtractor


def write(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _resources(units) -> set[str]:
    return set().union(*(u.resources for u in units))


def test_matches_set_and_invalidate_cluster_when_both_present(tmp_path):
    write(tmp_path, "writer.py", """
async def write():
    await cache.set_user(user_id, "profile_counts", {"x": 1})
""")
    write(tmp_path, "invalidator.py", """
async def invalidate():
    await cache.invalidate_user(user_id, "profile_counts")
""")

    units = list(CacheKeysExtractor().extract(tmp_path))
    # Both ops emit singleton resources (one for set, one for invalidate).
    # Use min_cluster_size=1 to expose singletons — they ARE the signal.
    clusters = group_by_resource_set(units, min_resources=1, min_cluster_size=1)
    by_resource = {next(iter(c.resources)): c for c in clusters}

    assert "set:profile_counts" in by_resource
    assert "invalidate:profile_counts" in by_resource


def test_set_without_invalidate_is_singleton(tmp_path):
    write(tmp_path, "writer.py", """
await cache.set_user(user_id, "missing_invalidator", value)
""")

    units = list(CacheKeysExtractor().extract(tmp_path))
    resources = _resources(units)
    assert "set:missing_invalidator" in resources
    assert "invalidate:missing_invalidator" not in resources


def test_fstring_prefix_captured(tmp_path):
    write(tmp_path, "writer.py", """
await cache.invalidate_user(user_id, f"liked_checkin:{checkin_id}")
""")

    units = list(CacheKeysExtractor().extract(tmp_path))
    resources = _resources(units)
    assert "invalidate:liked_checkin" in resources


def test_response_cache_set_no_user_arg(tmp_path):
    # response_cache.set(key, ...) — key at index 0, not 1.
    write(tmp_path, "mw.py", """
await response_cache.set("places_trending", payload, 300)
""")

    units = list(CacheKeysExtractor().extract(tmp_path))
    resources = _resources(units)
    assert "set:places_trending" in resources


def test_skips_computed_keys(tmp_path):
    write(tmp_path, "writer.py", """
await cache.set(some_variable, value)
await cache.set(compute_key(user_id), value)
""")

    units = list(CacheKeysExtractor().extract(tmp_path))
    # Computed keys aren't comparable — extractor stays silent.
    assert units == []


def test_wildcard_invalidate_pairs_with_concrete_set_keys(tmp_path):
    # Real circles-be pattern: writes go to ``unread:dm`` and
    # ``unread:group`` individually, but invalidation uses a single
    # wildcard ``unread:*``. Without expansion this looked like two
    # set-without-invalidator orphans. With expansion the wildcard
    # invalidate emits one synthetic Unit per covered set key, so the
    # cluster surfaces the real symmetry.
    write(tmp_path, "writer.py", """
await cache.set_user(user_id, "unread:dm", count)
await cache.set_user(user_id, "unread:group", count)
""")
    write(tmp_path, "evictor.py", """
await cache.invalidate_user(user_id, "unread:*")
""")

    units = list(CacheKeysExtractor().extract(tmp_path))
    resources = _resources(units)
    # Both concrete writes have explicit set Units.
    assert "set:unread:dm" in resources
    assert "set:unread:group" in resources
    # The wildcard call itself emits its literal resource AND one
    # synthetic invalidate per concrete set key it covers.
    assert "invalidate:unread:*" in resources
    assert "invalidate:unread:dm" in resources
    assert "invalidate:unread:group" in resources

    # The synthetic Units carry a ``via_wildcard`` marker so consumers
    # can distinguish them from literal invalidate calls.
    synthetic = [
        u for u in units
        if u.name in {"invalidate:unread:dm", "invalidate:unread:group"}
    ]
    assert all(u.extra.get("via_wildcard") == "unread:*" for u in synthetic)


def test_wildcard_does_not_match_across_segment_boundary(tmp_path):
    # ``unread:*`` covers ``unread:dm`` but must NOT cover
    # ``unreadable`` — the wildcard sits at a colon boundary.
    write(tmp_path, "writer.py", """
await cache.set_user(user_id, "unread:dm", count)
await cache.set_user(user_id, "unreadable", value)
""")
    write(tmp_path, "evictor.py", """
await cache.invalidate_user(user_id, "unread:*")
""")

    units = list(CacheKeysExtractor().extract(tmp_path))
    resources = _resources(units)
    assert "invalidate:unread:dm" in resources
    # ``unreadable`` must remain an orphan — wildcard does not cover it.
    assert "invalidate:unreadable" not in resources


def _resources(units):
    return set().union(*(u.resources for u in units))
