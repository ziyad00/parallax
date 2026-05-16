"""Smoke tests for the Pydantic / response-shape field extractor."""

from __future__ import annotations

from pathlib import Path

from parallax.extractors import DartJsonFieldsExtractor, PydanticFieldsExtractor


def write(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _resources(units) -> set[str]:
    return set().union(*(u.resources for u in units))


def test_extracts_pydantic_fields(tmp_path):
    write(tmp_path, "schemas.py", """
from pydantic import BaseModel

class PublicUserResponse(BaseModel):
    id: int
    name: str
    is_followed: bool
""")

    units = list(PydanticFieldsExtractor().extract(tmp_path))
    assert _resources(units) == {"id", "name", "is_followed"}


def test_extracts_dataclass_fields(tmp_path):
    write(tmp_path, "schemas.py", """
from dataclasses import dataclass

@dataclass
class FollowerCounts:
    followers: int
    following: int
""")

    units = list(PydanticFieldsExtractor().extract(tmp_path))
    assert _resources(units) == {"followers", "following"}


def test_picks_up_response_suffix_without_pydantic_base(tmp_path):
    # Plain class whose name ends in `Response` — the heuristic.
    write(tmp_path, "schemas.py", """
class FollowActionResponse:
    followed: bool
    status: str
""")

    units = list(PydanticFieldsExtractor().extract(tmp_path))
    assert _resources(units) == {"followed", "status"}


def test_ignores_unrelated_classes(tmp_path):
    # No BaseModel base, no @dataclass, no Response-suffix → skipped.
    write(tmp_path, "service.py", """
class FollowService:
    repo: object
    cache: object
""")

    units = list(PydanticFieldsExtractor().extract(tmp_path))
    assert units == []


def test_clusters_with_dart_json_field(tmp_path):
    # The cross-language case: backend field is `is_followed`; Dart
    # reads `json['is_followed']` → both emit the same resource.
    write(tmp_path, "backend/schemas.py", """
from pydantic import BaseModel

class PublicUserResponse(BaseModel):
    is_followed: bool
""")
    write(tmp_path, "flutter/model.dart", """
class UserModel {
  factory UserModel.fromJson(Map<String, dynamic> json) =>
      UserModel(isFollowed: json['is_followed'] as bool);
}
""")

    py_units = list(PydanticFieldsExtractor().extract(tmp_path))
    dart_units = list(DartJsonFieldsExtractor().extract(tmp_path))
    all_resources = _resources(py_units) | _resources(dart_units)
    assert "is_followed" in all_resources

    # And the languages are correctly tagged.
    langs = {u.language for u in py_units + dart_units}
    assert {"python", "dart"}.issubset(langs)
