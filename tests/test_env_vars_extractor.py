from pathlib import Path

from parallax.core import group_by_resource_set
from parallax.extractors import EnvVarsExtractor


def write(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_clusters_python_and_typescript_reading_same_var(tmp_path):
    write(tmp_path, "py/billing.py", '''
import os
KEY = os.environ["STRIPE_SECRET_KEY"]
WEBHOOK = os.getenv("STRIPE_WEBHOOK_SECRET")
''')
    write(tmp_path, "ts/payments.ts", '''
const key = process.env.STRIPE_SECRET_KEY;
const webhook = process.env["STRIPE_WEBHOOK_SECRET"];
''')

    units = list(EnvVarsExtractor().extract(tmp_path))
    clusters = group_by_resource_set(units, min_resources=2)
    assert clusters
    assert clusters[0].resources == frozenset(
        {"STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"}
    )
    files = {u.location for u in clusters[0].units}
    assert files == {"py/billing.py", "ts/payments.ts"}


def test_go_and_shell(tmp_path):
    write(tmp_path, "main.go", '''
addr := os.Getenv("DATABASE_URL")
key, _ := os.LookupEnv("API_KEY")
''')
    write(tmp_path, "deploy.sh", '''
#!/bin/bash
DB="${DATABASE_URL}"
KEY="$API_KEY"
''')

    units = list(EnvVarsExtractor().extract(tmp_path))
    clusters = group_by_resource_set(units, min_resources=2)
    matching = [c for c in clusters if c.resources == frozenset({"DATABASE_URL", "API_KEY"})]
    assert matching
