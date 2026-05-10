# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Cluster name-similarity bonus to the interestingness score.
- `fold_units_by_class` and `--fold-threshold` to collapse N+ methods of the same class into a single report row.

## [0.2.0]

### Added
- Cluster scoring by interestingness (size, breadth, resource rarity, cross-file factor). Score is included in JSON, HTML, and SARIF output.
- `--top N` flag to limit the report to the highest-scoring clusters.
- `--cross-file-only` flag to drop clusters confined to one file.
- `redis-keys` receiver allow-list. Eliminates false positives like `dict.get(...)` and `params.get(...)`.

### Changed
- `group_by_resource_set` sorts by score (descending), then size, then resource count.

## [0.1.0]

### Added
- Initial release.
- Core grouping engine.
- Built-in extractors: `sqlalchemy`, `django`, `http-urls`, `env-vars`, `redis-keys`.
- Reporters: text, JSON, HTML, SARIF v2.1.0.
- `.parallax.toml` config with `[scan]`, `[ci]`, repeated `[[ignore]]` blocks.
- `--ci` flag for threshold-based exit.

[Unreleased]: https://github.com/ziyad00/parallax/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ziyad00/parallax/releases/tag/v0.2.0
[0.1.0]: https://github.com/ziyad00/parallax/releases/tag/v0.1.0
