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
    files = {u.location for u in matching[0].units}
    assert files == {"py/billing.py", "ts/payments.ts"}


def test_normalize_url_collapses_path_params(tmp_path):
    write(tmp_path, "a.py", 'url = "/v1/users/123/orders"')
    write(tmp_path, "b.go", 'url := "/v1/users/456/orders"')

    units = list(HttpUrlExtractor().extract(tmp_path))
    # Both resolve to the same canonical resource.
    resources = set().union(*(u.resources for u in units))
    assert "/v1/users/{id}/orders" in resources
