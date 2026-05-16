"""Smoke tests for the Dart ApiEndpoints-resolving extractor."""

from __future__ import annotations

from pathlib import Path

from parallax.core import group_by_resource_set
from parallax.extractors import (
    DartApiCallExtractor,
    FastApiRoutesExtractor,
    HttpUrlExtractor,
)


def write(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _resources(units) -> set[str]:
    return set().union(*(u.resources for u in units))


def test_resolves_interpolated_constant_in_call_site(tmp_path):
    # The exact pattern that defeats http-urls in circles-flutter-app:
    # the call site interpolates a constant + a path param.
    write(tmp_path, "api_endpoints.dart", """
class ApiEndpoints {
  static const String follow = '/follow';
}
""")
    write(tmp_path, "data_source.dart", """
Future<void> unfollow(int userId) async {
  final path = '${ApiEndpoints.follow}/$userId';
  await _dio.delete(path);
}
""")

    units = list(DartApiCallExtractor().extract(tmp_path))
    assert _resources(units) == {"/follow/{id}"}
    # And the Unit is attributed to the data source — where the bug lives.
    locations = {u.location.split(":", 1)[0] for u in units}
    assert "data_source.dart" in locations


def test_resolves_static_method_constant(tmp_path):
    write(tmp_path, "api.dart", """
class ApiEndpoints {
  static String cancelFollowRequest(int userId) =>
      '/follow/requests/$userId';
}
""")
    write(tmp_path, "caller.dart", """
await _dio.delete('${ApiEndpoints.cancelFollowRequest}/something');
""")

    units = list(DartApiCallExtractor().extract(tmp_path))
    # The lambda body's `$userId` collapses to {id}; the literal
    # `/something` is preserved.
    assert _resources(units) == {"/follow/requests/{id}/something"}


def test_no_constant_class_yields_no_units(tmp_path):
    # If the codebase has no ApiEndpoints-style class, this extractor
    # should stay silent and let http-urls do its thing.
    write(tmp_path, "x.dart", """
final path = '/literal/path';
""")

    units = list(DartApiCallExtractor().extract(tmp_path))
    assert units == []


def test_clusters_with_fastapi_route(tmp_path):
    # End-to-end: backend declares /follow/requests/{user_id}, Flutter
    # data source interpolates the corresponding ApiEndpoints method.
    # Both should land in the same cluster.
    write(tmp_path, "backend/main.py", """
from fastapi import FastAPI
from .routers.follow import router as follow_router

app = FastAPI()
app.include_router(follow_router, prefix="/follow")
""")
    write(tmp_path, "backend/routers/__init__.py", "")
    write(tmp_path, "backend/routers/follow.py", """
from fastapi import APIRouter

router = APIRouter()

@router.delete("/requests/{user_id}")
async def cancel_follow_request(user_id: int): ...
""")
    write(tmp_path, "flutter/api_endpoints.dart", """
class ApiEndpoints {
  static String cancelFollowRequest(int userId) =>
      '/follow/requests/$userId';
}
""")
    write(tmp_path, "flutter/data_source.dart", """
await _dio.delete('${ApiEndpoints.cancelFollowRequest}');
""")

    units = []
    units += list(FastApiRoutesExtractor().extract(tmp_path))
    units += list(HttpUrlExtractor().extract(tmp_path))
    units += list(DartApiCallExtractor().extract(tmp_path))
    clusters = group_by_resource_set(units, min_resources=1)

    match = [c for c in clusters if "/follow/requests/{id}" in c.resources]
    assert len(match) == 1
    files = {u.location.split(":", 1)[0] for u in match[0].units}
    assert "backend/routers/follow.py" in files
    assert "flutter/api_endpoints.dart" in files
    assert "flutter/data_source.dart" in files


def test_ignores_plain_interpolations_without_class_ref(tmp_path):
    # `$bar` without a class qualifier shouldn't fire — that's just a
    # generic string and would produce huge noise.
    write(tmp_path, "api.dart", """
class ApiEndpoints {
  static const String hello = '/hello';
}
""")
    write(tmp_path, "logging.dart", """
print('User logged in: $username');
final msg = 'Count: $count';
""")

    units = list(DartApiCallExtractor().extract(tmp_path))
    assert units == []
