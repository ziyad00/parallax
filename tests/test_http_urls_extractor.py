"""Smoke tests for the language-agnostic HTTP URL extractor."""

from __future__ import annotations

from pathlib import Path

from parallax.core import group_by_resource_set
from parallax.extractors import HttpUrlExtractor


def write(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_clusters_python_and_typescript_touching_same_endpoint(tmp_path):
    # Same logical endpoint, two different languages, two different
    # http clients.
    write(tmp_path, "py/billing.py", '''
import httpx
def charge(amount):
    return httpx.post("https://api.stripe.com/v1/charges", json={"amount": amount})
''')
    write(tmp_path, "ts/payments.ts", '''
import axios from "axios";
export async function pay(amount: number) {
  return axios.post("https://api.stripe.com/v1/charges", { amount });
}
''')

    units = list(HttpUrlExtractor().extract(tmp_path))
    clusters = group_by_resource_set(units, min_resources=1)
    # One cluster containing both files, resource = "/v1/charges".
    matching = [c for c in clusters if "/v1/charges" in c.resources]
    assert len(matching) == 1
    files = {u.location.split(":", 1)[0] for u in matching[0].units}
    assert files == {"py/billing.py", "ts/payments.ts"}


def test_normalize_url_collapses_path_params(tmp_path):
    write(tmp_path, "a.py", 'url = "/v1/users/123/orders"')
    write(tmp_path, "b.go", 'url := "/v1/users/456/orders"')

    units = list(HttpUrlExtractor().extract(tmp_path))
    # Both resolve to the same canonical resource.
    resources = set().union(*(u.resources for u in units))
    assert "/v1/users/{id}/orders" in resources


def test_fastapi_route_and_dart_call_cluster_on_same_endpoint(tmp_path):
    # Models the cancel-follow bug class: a FastAPI route declared in
    # the backend should cluster with its Dart caller so unmatched
    # callers / unused routes show up as singletons.
    write(tmp_path, "backend/follow.py", '''
@router.delete("/follow/requests/{user_id}")
async def cancel_follow_request(user_id: int):
    ...
''')
    write(tmp_path, "flutter/api_endpoints.dart", '''
class ApiEndpoints {
  static String cancelFollowRequest(int userId) =>
      "/follow/requests/$userId";
}
''')

    units = list(HttpUrlExtractor().extract(tmp_path))
    clusters = group_by_resource_set(units, min_resources=1)
    matching = [c for c in clusters if "/follow/requests/{id}" in c.resources]
    assert len(matching) == 1, (
        "Backend route + Dart caller must cluster on the same normalized URL"
    )
    files = {u.location.split(":", 1)[0] for u in matching[0].units}
    assert "backend/follow.py" in files
    assert "flutter/api_endpoints.dart" in files


def test_singleton_call_surfaces_orphan_dart_url(tmp_path):
    # If a Dart file references a URL no Python file declares, the
    # cluster is a singleton — exactly the signal we want for "Flutter
    # is calling an endpoint the backend never exposes".
    write(tmp_path, "backend/follow.py", '''
@router.delete("/follow/{user_id}")
async def unfollow_user(user_id: int): ...
''')
    write(tmp_path, "flutter/datasource.dart", '''
final res = await _dio.delete("/follow/requests/$userId");
''')

    units = list(HttpUrlExtractor().extract(tmp_path))
    clusters = group_by_resource_set(units, min_resources=1, min_cluster_size=1)
    by_resource = {next(iter(c.resources)): c for c in clusters if len(c.resources) == 1}

    orphan = by_resource["/follow/requests/{id}"]
    assert orphan.size == 1
    assert next(iter(orphan.units)).location.startswith("flutter/datasource.dart")

    backend_only = by_resource["/follow/{id}"]
    assert backend_only.size == 1
    assert next(iter(backend_only.units)).location.startswith("backend/follow.py")


def test_dart_dollar_brace_interpolation_normalizes(tmp_path):
    write(tmp_path, "a.dart", '''var x = "/users/${userId}/posts/${postId}";''')
    write(tmp_path, "b.py", '''@app.get("/users/{user_id}/posts/{post_id}")''')

    units = list(HttpUrlExtractor().extract(tmp_path))
    resources = set().union(*(u.resources for u in units))
    assert "/users/{id}/posts/{id}" in resources
