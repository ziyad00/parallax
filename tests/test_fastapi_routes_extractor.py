"""Smoke tests for the FastAPI routes extractor."""

from __future__ import annotations

from pathlib import Path

from parallax.core import group_by_resource_set
from parallax.extractors import FastApiRoutesExtractor, HttpUrlExtractor


def write(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _resources(units) -> set[str]:
    return set().union(*(u.resources for u in units))


def test_resolves_router_prefix(tmp_path):
    write(tmp_path, "follow.py", """
from fastapi import APIRouter

router = APIRouter(prefix="/follow")

@router.delete("/requests/{user_id}")
async def cancel_follow_request(user_id: int): ...

@router.delete("/{user_id}")
async def unfollow_user(user_id: int): ...
""")

    units = list(FastApiRoutesExtractor().extract(tmp_path))
    resources = _resources(units)
    assert "/follow/requests/{id}" in resources
    assert "/follow/{id}" in resources


def test_no_prefix_yields_raw_path(tmp_path):
    write(tmp_path, "health.py", """
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health(): ...
""")

    units = list(FastApiRoutesExtractor().extract(tmp_path))
    assert _resources(units) == {"/health"}


def test_method_preserved_in_extra(tmp_path):
    write(tmp_path, "users.py", """
from fastapi import APIRouter

router = APIRouter(prefix="/users")

@router.post("/{user_id}/follow")
async def follow_user(user_id: int): ...

@router.delete("/{user_id}/follow")
async def unfollow_user(user_id: int): ...
""")

    units = list(FastApiRoutesExtractor().extract(tmp_path))
    by_method = {u.extra.get("method"): u for u in units}
    assert by_method["POST"].resources == frozenset({"/users/{id}/follow"})
    assert by_method["DELETE"].resources == frozenset({"/users/{id}/follow"})


def test_skips_non_string_path(tmp_path):
    # f-strings and computed paths are skipped — too noisy and rare.
    write(tmp_path, "x.py", """
from fastapi import APIRouter
router = APIRouter(prefix="/x")
base = "/y"

@router.get(f"/dynamic/{base}")
async def dyn(): ...

@router.get("/static")
async def stc(): ...
""")

    units = list(FastApiRoutesExtractor().extract(tmp_path))
    assert _resources(units) == {"/x/static"}


def test_clusters_with_http_urls_dart_caller(tmp_path):
    # End-to-end: fastapi-routes + http-urls produce a single
    # cross-language cluster on the same normalized URL — exactly the
    # signal needed to catch backend-vs-frontend drift like the
    # cancel-follow bug.
    write(tmp_path, "backend/follow.py", """
from fastapi import APIRouter

router = APIRouter(prefix="/follow")

@router.delete("/requests/{user_id}")
async def cancel_follow_request(user_id: int): ...
""")
    write(tmp_path, "flutter/datasource.dart", """
class DataSource {
  Future<void> cancel(int userId) async {
    await _dio.delete("/follow/requests/$userId");
  }
}
""")

    units = list(FastApiRoutesExtractor().extract(tmp_path))
    units += list(HttpUrlExtractor().extract(tmp_path))
    clusters = group_by_resource_set(units, min_resources=1)

    cancel = [c for c in clusters if "/follow/requests/{id}" in c.resources]
    assert len(cancel) == 1
    languages = {u.language for u in cancel[0].units}
    assert {"python", "dart"}.issubset(languages)


def test_include_router_prefix_resolved_across_files(tmp_path):
    # The pattern circles-be uses: prefix lives on app.include_router in
    # main.py, NOT on the APIRouter declaration in routers/follow.py.
    # Without cross-file resolution, the route surfaces as `/{user_id}`
    # rather than `/follow/{user_id}` — invisible to drift detection.
    write(tmp_path, "app/main.py", """
from fastapi import FastAPI
from .routers.follow import router as follow_router

app = FastAPI()
app.include_router(follow_router, prefix="/follow")
""")
    write(tmp_path, "app/routers/follow.py", """
from fastapi import APIRouter

router = APIRouter(tags=["follow"])

@router.post("/{user_id}")
async def follow_user(user_id: int): ...

@router.delete("/requests/{user_id}")
async def cancel_follow_request(user_id: int): ...
""")
    write(tmp_path, "app/routers/__init__.py", "")

    units = list(FastApiRoutesExtractor().extract(tmp_path))
    resources = _resources(units)
    assert "/follow/{id}" in resources
    assert "/follow/requests/{id}" in resources


def test_include_router_combines_with_router_level_prefix(tmp_path):
    # A router can have its own prefix AND be included with another
    # prefix on top; the result is the concatenation.
    write(tmp_path, "main.py", """
from fastapi import FastAPI
from .v2 import router as v2_router

app = FastAPI()
app.include_router(v2_router, prefix="/api")
""")
    write(tmp_path, "v2.py", """
from fastapi import APIRouter

router = APIRouter(prefix="/v2")

@router.get("/users/{user_id}")
async def get_user(user_id: int): ...
""")

    units = list(FastApiRoutesExtractor().extract(tmp_path))
    assert _resources(units) == {"/api/v2/users/{id}"}


def test_orphan_route_is_singleton(tmp_path):
    # A backend route with no Dart caller surfaces as a singleton
    # cluster — the "dead route" signal.
    write(tmp_path, "backend/forgotten.py", """
from fastapi import APIRouter

router = APIRouter(prefix="/legacy")

@router.get("/forgotten")
async def forgotten(): ...
""")
    # Flutter file mentions a different URL.
    write(tmp_path, "flutter/api.dart", """
final url = "/v2/active";
""")

    units = list(FastApiRoutesExtractor().extract(tmp_path))
    units += list(HttpUrlExtractor().extract(tmp_path))
    clusters = group_by_resource_set(units, min_resources=1, min_cluster_size=1)
    by_url = {next(iter(c.resources)): c for c in clusters}

    assert by_url["/legacy/forgotten"].size == 1
    assert next(iter(by_url["/legacy/forgotten"].units)).language == "python"
