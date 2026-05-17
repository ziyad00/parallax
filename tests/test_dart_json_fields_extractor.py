"""Smoke tests for the Dart json[...] field extractor."""

from __future__ import annotations

from pathlib import Path

from parallax.extractors import DartJsonFieldsExtractor


def write(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _resources(units) -> set[str]:
    return set().union(*(u.resources for u in units))


def test_extracts_single_and_double_quote_keys(tmp_path):
    write(tmp_path, "model.dart", """
final id = json['id'] as int;
final name = json["name"] as String;
""")

    units = list(DartJsonFieldsExtractor().extract(tmp_path))
    assert _resources(units) == {"id", "name"}


def test_deduplicates_within_a_file(tmp_path):
    write(tmp_path, "model.dart", """
final a = json['id'] as int;
final b = json['id'] as int?;
final c = json['id'];
""")

    units = list(DartJsonFieldsExtractor().extract(tmp_path))
    # One Unit, one location — the first occurrence.
    assert len(units) == 1
    assert next(iter(units)).resources == frozenset({"id"})


def test_ignores_dynamic_keys(tmp_path):
    write(tmp_path, "model.dart", """
final v = json[someKey];
final w = json['${prefix}suffix'];
""")

    units = list(DartJsonFieldsExtractor().extract(tmp_path))
    # The interpolated key isn't a literal — currently captured as
    # ``${prefix}suffix`` (the regex match), which is fine; the
    # important property is that ``someKey`` (variable lookup) is
    # NOT captured.
    keys = _resources(units)
    assert "someKey" not in keys


def test_skips_local_storage_files(tmp_path):
    # Local-cache helpers persist a class to disk via toJson/fromJson
    # in a shape that has nothing to do with the wire API. Skip them
    # so the orphan signal isn't drowned in cache-shape noise.
    write(tmp_path, "feature/chat/data/data_sources/local/message_local_storage.dart", """
class MessageLocalStorage {
  Map<String, dynamic> toJson() => {'backendId': id, 'authorAvatar': avatar};
  factory MessageLocalStorage.fromJson(Map<String, dynamic> json) =>
      MessageLocalStorage(backendId: json['backendId'], authorAvatar: json['authorAvatar']);
}
""")
    write(tmp_path, "feature/profile/wire_model.dart", """
class ProfileResponse {
  factory ProfileResponse.fromJson(Map<String, dynamic> json) =>
      ProfileResponse(name: json['name']);
}
""")

    units = list(DartJsonFieldsExtractor().extract(tmp_path))
    resources = _resources(units)
    # Wire model survives.
    assert "name" in resources
    # Local-storage keys are filtered.
    assert "backendId" not in resources
    assert "authorAvatar" not in resources


def test_ignore_path_patterns_is_overridable(tmp_path):
    # The default skip list is project-tunable.
    write(tmp_path, "thing_local_storage.dart", """
final x = json['kept_after_override'];
""")

    units = list(
        DartJsonFieldsExtractor(ignore_path_patterns=()).extract(tmp_path)
    )
    assert _resources(units) == {"kept_after_override"}
