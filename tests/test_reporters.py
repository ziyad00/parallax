"""Smoke tests for the four reporters."""

from __future__ import annotations

import json

from parallax.core import Cluster, Unit
from parallax.reporters import render_html, render_json, render_sarif, render_text


def make_clusters() -> list[Cluster]:
    a = Unit(location="api/users.py:42", name="get_user", resources=frozenset({"User", "Order"}), language="python")
    b = Unit(location="services/billing.py:17", name="bill_user", resources=frozenset({"User", "Order"}), language="python")
    return [Cluster(resources=frozenset({"User", "Order"}), units=[a, b])]


def test_text_includes_summary_and_cluster_lines():
    out = render_text(
        make_clusters(),
        scanned_units=99,
        extractors=["sqlalchemy"],
        min_resources=2,
        min_cluster_size=2,
    )
    assert "Scanned 99 units" in out
    assert "['Order', 'User']" in out
    assert "api/users.py:42::get_user" in out
    assert "services/billing.py:17::bill_user" in out


def test_json_is_valid_and_complete():
    out = render_json(make_clusters(), scanned_units=99)
    parsed = json.loads(out)
    assert parsed["scanned"] == 99
    assert len(parsed["clusters"]) == 1
    cl = parsed["clusters"][0]
    assert cl["resources"] == ["Order", "User"]
    assert cl["size"] == 2
    assert {u["location"] for u in cl["units"]} == {
        "api/users.py:42",
        "services/billing.py:17",
    }


def test_html_is_self_contained_and_escapes_input():
    sneaky = Unit(
        location="<bad>.py:1",
        name="<script>alert(1)</script>",
        resources=frozenset({"<x>", "<y>"}),
        language="python",
    )
    cluster = Cluster(resources=frozenset({"<x>", "<y>"}), units=[sneaky, sneaky])
    out = render_html(
        [cluster],
        scanned_units=1,
        extractors=["sqlalchemy"],
        min_resources=1,
        min_cluster_size=2,
    )
    assert "<!doctype html>" in out
    assert "<style>" in out  # css is inline
    # No raw script tag should make it through
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_sarif_is_valid_v2_1_0():
    out = render_sarif(make_clusters(), scanned_units=99, extractors=["sqlalchemy"])
    parsed = json.loads(out)
    assert parsed["version"] == "2.1.0"
    assert parsed["runs"][0]["tool"]["driver"]["name"] == "parallax"
    rules = parsed["runs"][0]["tool"]["driver"]["rules"]
    assert any(r["id"] == "PARA001" for r in rules)
    results = parsed["runs"][0]["results"]
    assert len(results) == 1
    res = results[0]
    assert res["ruleId"] == "PARA001"
    assert res["locations"][0]["physicalLocation"]["region"]["startLine"] == 42
    assert res["relatedLocations"][0]["physicalLocation"]["region"]["startLine"] == 17


def test_html_empty_state():
    out = render_html(
        [],
        scanned_units=0,
        extractors=["sqlalchemy"],
        min_resources=2,
        min_cluster_size=2,
    )
    assert "No clusters found" in out
