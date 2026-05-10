# Changelog

All notable changes to **parallax** will be documented here. The format
is loosely based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-05-10
### Added
- Initial release.
- Core grouping engine: cluster units by their resource set.
- Pluggable extractors:
  - `sqlalchemy` — Python AST + ORM model classes.
  - `django` — Python AST + Django ORM models (`models.Model` subclasses).
  - `http-urls` — language-agnostic regex for HTTP URL paths in any text source.
  - `env-vars` — language-agnostic regex for environment-variable reads (Python, JS/TS, Go, Rust, shell).
  - `redis-keys` — language-agnostic regex for Redis key namespaces (redis-py, ioredis, node-redis, go-redis).
- Reporters: text, JSON, HTML (self-contained, escapes HTML), SARIF v2.1.0.
- Config file (`.parallax.toml`) with `[scan]`, `[ci]`, repeated `[[ignore]]` blocks.
- `--ci` flag — fail only when a cluster meets `config.ci.max_cluster_size`.
- CLI: `parallax scan PATH [--extractor NAME]* [--format {text,json,html,sarif}] [--output FILE] [--ci]`.

[Unreleased]: https://github.com/ziyad00/parallax/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ziyad00/parallax/releases/tag/v0.1.0
