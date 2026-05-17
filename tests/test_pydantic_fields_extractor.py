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


def test_case_canonical_clusters_camel_with_snake(tmp_path):
    # Backend Pydantic uses snake_case; Flutter reads camelCase.
    # Without canonicalisation these were separate clusters; with
    # canonicalisation they land in the same one.
    write(tmp_path, "backend/schemas.py", """
from pydantic import BaseModel

class UserResponse(BaseModel):
    is_followed: bool
    avatar_url: str
""")
    write(tmp_path, "flutter/model.dart", """
class UserModel {
  factory UserModel.fromJson(Map<String, dynamic> json) =>
      UserModel(
        isFollowed: json['isFollowed'] as bool,
        avatarUrl: json['avatarUrl'] as String,
      );
}
""")

    py_units = list(PydanticFieldsExtractor().extract(tmp_path))
    dart_units = list(DartJsonFieldsExtractor().extract(tmp_path))
    resources = _resources(py_units) | _resources(dart_units)

    # Canonicalised to snake_case on BOTH sides.
    assert resources == {"is_followed", "avatar_url"}
    # Original spellings are preserved in Unit.name / extra so reports
    # can show the actual wire string.
    raw_dart_fields = {u.extra.get("raw_field") for u in dart_units}
    assert raw_dart_fields == {"isFollowed", "avatarUrl"}


def test_inline_dict_in_broadcast_emits_fields(tmp_path):
    # The discover-wave case: response shape lives inline in a
    # broadcast helper call, not in a Pydantic class.
    write(tmp_path, "backend/discover.py", """
async def on_wave(websocket, to_user_id, sender, result, data):
    await broadcast_to_user(
        to_user_id,
        {
            "type": "wave_received",
            "wave_id": result.get("wave_id"),
            "from_user": {"user_id": sender.id},
            "message": data.get("message"),
        },
    )
""")

    units = list(PydanticFieldsExtractor().extract(tmp_path))
    resources = _resources(units)
    # Top-level keys are picked up; nested dict values are NOT
    # recursed into (only the outer wire shape matters).
    assert {"type", "wave_id", "from_user", "message"}.issubset(resources)
    # Each Unit knows it came from a broadcast helper for downstream
    # filtering / reporting.
    broadcast_units = [u for u in units if u.extra.get("broadcast")]
    assert all(u.extra["broadcast"] == "broadcast_to_user" for u in broadcast_units)


def test_inline_dict_skipped_for_unrecognised_function(tmp_path):
    # ``some_random_function({"key": ...})`` is NOT a broadcast and
    # mustn't be mined for fields — that would pollute the cluster
    # space.
    write(tmp_path, "x.py", """
def do_stuff():
    payload = some_random_function({"random_key": 1, "another": 2})
""")

    units = list(PydanticFieldsExtractor().extract(tmp_path))
    assert _resources(units) == set()
