# parallax

[![PyPI version](https://img.shields.io/pypi/v/parallax-scan.svg)](https://pypi.org/project/parallax-scan/)
[![CI](https://github.com/ziyad00/parallax/actions/workflows/ci.yml/badge.svg)](https://github.com/ziyad00/parallax/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Find code that does the same logical job through different paths.

Token-similarity tools (jscpd, PMD CPD, `pylint duplicate-code`) detect copy-paste. parallax detects something different: two pieces of code that touch the same set of resources, regardless of how the code is written. Different filters, different return shapes, even different languages.

## Model

A **unit** of code (function, method, file, module, microservice, ...) touches a set of **resources** (database tables, HTTP endpoints, Redis keys, env vars, file paths, ...). Units sharing the same resource set are clustered as duplication candidates.

Both unit detection and resource detection are pluggable per **extractor**.

## Built-in extractors

| Name | Unit | Resource |
|---|---|---|
| `sqlalchemy` | Python function/method | SQLAlchemy ORM model classes |
| `django` | Python function/method | Django ORM model classes |
| `sequelize` | TypeScript / JS function/method | TypeORM `@Entity` / Sequelize `Model` classes (requires `[treesitter]` extra) |
| `fastapi-routes` | Python function/method | FastAPI route path (resolves `APIRouter(prefix=...)` + `app.include_router(..., prefix=...)` across files) |
| `dart-api-calls` | Dart string literal | URL templates resolved by substituting `${ClassName.member}` interpolations against `static [const] String member = '...';` / `static String member(...) => '...';` declarations elsewhere in the tree |
| `pydantic-fields` | Pydantic / dataclass / *Response class field | Field name — clusters with `dart-json-fields` for response-shape drift detection |
| `dart-json-fields` | Dart `json['X']` access | Field name — clusters with `pydantic-fields` |
| `cache-keys` | `cache.set` / `cache.invalidate` call | `set:{key}` or `invalidate:{key}` — singleton on either side flags a missing write/invalidate counterpart |
| `http-urls` | any text file (incl. `.dart`) | HTTP URL paths (one Unit per file × URL; FastAPI `{param}` and Dart `$var` / `${var}` interpolation collapse to `{id}`) |
| `env-vars` | any text file | Environment variable names |
| `redis-keys` | any text file | Redis key namespaces |

## Installation

```bash
pip install parallax-scan
pip install "parallax-scan[treesitter]"   # adds the sequelize extractor
```

## Usage

```bash
parallax scan path/to/repo
parallax scan path/to/repo --extractor sqlalchemy
parallax scan path/to/repo -e sqlalchemy -e http-urls
parallax scan path/to/repo --min-resources 3 --top 20
parallax scan path/to/repo --cross-file-only
parallax scan path/to/repo --format html -o report.html
parallax scan path/to/repo --format sarif -o parallax.sarif

# axis-coverage: bucket code paths by which subset of a feature axis
# they touch. Surfaces "this file handles DM and Group but forgot
# Place chat" gaps that cross-cutting refactors keep regressing.
parallax axis path/to/repo -e sqlalchemy \
  --axis DMThread,GroupChat,PlaceChatMessage
```

## Configuration

Drop `.parallax.toml` at your repo root:

```toml
[scan]
min_resources = 3
min_cluster_size = 2

[ci]
max_cluster_size = 5

[[ignore]]
resources = ["User", "Place"]
reason = "Generic"
```

In CI:

```bash
parallax scan . --ci
parallax scan . --format sarif -o parallax.sarif
```

`--ci` exits non-zero only when a cluster meets `ci.max_cluster_size`. Without it, any cluster is non-zero.

## Comparison

| Tool | Catches | Doesn't catch |
|---|---|---|
| jscpd, PMD CPD, pylint duplicate-code | Token-similar copy-paste | Code with different surface shape |
| Sourcegraph | Manual code search | Automatic detection |
| `pydeps`, `dependency-cruiser` | Module-level imports | Same-resource overlap |
| semgrep | Hand-written patterns | Discovery |
| parallax | Same-resource overlap regardless of shape | Single-instance bad patterns |

## Status

Alpha. API and CLI are unstable until 1.0.

## Writing an extractor

```python
from pathlib import Path
from typing import Iterable

from parallax import Unit
from parallax.extractors.base import Extractor


class TerraformAwsExtractor(Extractor):
    name = "terraform-aws"

    def extract(self, root: Path) -> Iterable[Unit]:
        for tf in root.rglob("*.tf"):
            ...
```

Register in `parallax.extractors.BUILTIN_EXTRACTORS`.

## License

MIT
