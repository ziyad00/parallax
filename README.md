# parallax

[![PyPI version](https://img.shields.io/pypi/v/parallax-scan.svg)](https://pypi.org/project/parallax-scan/)
[![CI](https://github.com/ziyad00/parallax/actions/workflows/ci.yml/badge.svg)](https://github.com/ziyad00/parallax/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Find code that does the same logical job through different paths.
> Language-, unit-, and resource-agnostic.

Token-similarity tools (jscpd, PMD CPD, `pylint --enable=duplicate-code`) find **copy-paste** — the same lines appearing twice. They miss the more dangerous kind of duplication: two pieces of code, written by different people at different times, that do the same logical job through totally different code.

That's what parallax finds.

## What "same logical job" means

The tool is built around a single generic idea:

> A **unit** of code (any granularity, any language) touches a set of **resources** (any kind: tables, URLs, files, queues, env vars, config keys, ...). Units that touch the same resource set are doing the same logical job and are candidates for consolidation.

What's a unit?

- A function or method
- A class
- A whole file or module
- A microservice
- A Terraform resource block
- A Kubernetes manifest

What's a resource?

- A database table or view
- An HTTP endpoint URL
- A Redis key prefix
- A file path or S3 bucket
- A Kafka topic
- An environment variable
- A configuration key
- An external service / DNS name

Both the unit definition and the resource definition are pluggable per **extractor**. parallax ships with two built-in extractors and a clear interface to add more.

## Built-in extractors

| Name | Language(s) | Unit | Resource |
|---|---|---|---|
| `sqlalchemy` | Python | function/method | SQLAlchemy ORM model classes referenced |
| `http-urls` | any text | file | HTTP URL paths mentioned (axios, requests, curl, fetch, http.Get, ...) |

More are planned: Django ORM, Sequelize / TypeORM, generic tree-sitter for any language with a parser, Terraform, Kafka clients, Redis key patterns, environment-variable readers, Kubernetes service references.

## Examples of what it catches

- Two REST endpoints joining the same DB tables but with different filters and response shapes — they look unrelated to jscpd because the field names diverge, but they're answering the same question.
- Three repository methods that UNION the same activity tables to count "active users" — when the canonical activity definition changes, all three need updating.
- Five services that POST to the same external API endpoint, each with their own retry / timeout / logging code — none copy-pasted from the others, but all reimplementing the same integration.
- Two scripts that read and parse the same config file — one in Python, one in Bash. Same job, different language.

## Installation

```bash
pip install parallax-scan
```

## Quick start

```bash
# Run every built-in extractor against a repo
parallax scan path/to/your/repo

# Just the SQLAlchemy extractor
parallax scan path/to/your/repo --extractor sqlalchemy

# Combine extractors
parallax scan path/to/your/repo -e sqlalchemy -e http-urls

# Filter the noise floor (skip clusters with too few distinct resources)
parallax scan path/to/your/repo --min-resources 3

# Output formats: text (default), json, html, sarif
parallax scan path/to/your/repo --format html -o report.html
parallax scan path/to/your/repo --format sarif -o parallax.sarif
```

`--format sarif` produces a [SARIF v2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/) document that GitHub Code Scanning uploads via `actions/upload-sarif` — clusters render as PR annotations.

## Config + CI mode

Drop a `.parallax.toml` at your repo root:

```toml
[scan]
min_resources = 3
min_cluster_size = 2

[ci]
# Hard-fail the CI run only when a cluster has 5+ members.
max_cluster_size = 5

# Suppress clusters you've decided not to fix yet.
[[ignore]]
resources = ["User", "Place"]
reason = "Generic — touched by 200 endpoints"

[[ignore]]
resources = ["session"]
reason = "Session cache is intentionally accessed everywhere"
```

Then in CI:

```bash
parallax scan . --ci          # exit non-zero only past max_cluster_size
parallax scan . --format sarif -o parallax.sarif
```

Without `--ci`, exit is non-zero on any cluster — fine for local runs and PR review, but too noisy for new pipelines. With `--ci`, parallax only fails when something exceeds the threshold you've agreed on.

## How it differs from existing tools

| Tool | Catches | Doesn't catch |
|---|---|---|
| **jscpd**, **PMD CPD**, **pylint duplicate-code** | Copy-paste (token similarity) | Anything that's not byte-similar |
| **Sourcegraph** | Manual code search | Doesn't *detect* — you have to hypothesise |
| **`pydeps`**, **`dependency-cruiser`** | Module-level imports | Same-resource overlap |
| **semgrep** | Hand-written patterns | Automatic discovery (you have to know what to look for) |
| **parallax** | Same-resource overlap regardless of code shape | Single-instance bad patterns (use semgrep for those) |

Use parallax alongside the others — they cover different layers.

## Status

**Alpha.** API and CLI are unstable until 1.0. The first shipping extractor (SQLAlchemy ORM) was motivated by real architectural duplication that jscpd had already passed clean. The HTTP-URL extractor demonstrates that the generalisation works across languages.

## Writing a new extractor

```python
from pathlib import Path
from typing import Iterable

from parallax import Unit
from parallax.extractors.base import Extractor


class TerraformAwsExtractor(Extractor):
    name = "terraform-aws"

    def extract(self, root: Path) -> Iterable[Unit]:
        for tf in root.rglob("*.tf"):
            # parse, find aws_* resource blocks, identify which AWS
            # resources the module touches, yield Unit(...)
            ...
```

Then register it in `BUILTIN_EXTRACTORS` (or load it as a plugin once that mechanism lands).

## Contributing

Issues and PRs welcome. Especially:

- New extractors for more languages and resource types
- HTML / SARIF output (so GitHub can annotate PRs)
- A CI mode with allow-lists and thresholds

## License

MIT
