"""Command-line interface for parallax."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import Config, load_config
from .core import Cluster, Unit, group_by_resource_set
from .extractors import BUILTIN_EXTRACTORS
from .reporters import render_html, render_json, render_sarif, render_text


REPORTERS = {"text", "json", "html", "sarif"}


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="parallax",
        description=(
            "Find code that does the same logical job through different paths. "
            "Language-, unit-, and resource-agnostic."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan a tree for clusters of overlapping units.")
    scan.add_argument("path", type=Path, help="Root directory to scan.")
    scan.add_argument(
        "--extractor",
        "-e",
        action="append",
        choices=sorted(BUILTIN_EXTRACTORS),
        help="Which extractor to run. Repeat to combine. Default: all.",
    )
    scan.add_argument(
        "--config",
        "-c",
        type=Path,
        help=(
            "Path to a config file (TOML). If omitted, parallax looks for "
            ".parallax.toml in the working directory."
        ),
    )
    scan.add_argument(
        "--min-resources",
        type=int,
        help="Override config.scan.min_resources.",
    )
    scan.add_argument(
        "--min-cluster-size",
        type=int,
        help="Override config.scan.min_cluster_size.",
    )
    scan.add_argument(
        "--format",
        "-f",
        choices=sorted(REPORTERS),
        default="text",
        help="Output format. Default 'text'.",
    )
    scan.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Write output to FILE instead of stdout.",
    )
    scan.add_argument(
        "--json",
        action="store_true",
        help="Shortcut for --format json.",
    )
    scan.add_argument(
        "--ci",
        action="store_true",
        help=(
            "CI mode: exit non-zero only if a cluster exceeds "
            "config.ci.max_cluster_size. Without this flag, any cluster "
            "produces exit 1."
        ),
    )

    sub.add_parser("list-extractors", help="Print the extractors built into parallax.")

    return p


def _apply_overrides(args: argparse.Namespace, cfg: Config) -> Config:
    """CLI flags trump config-file values when given."""
    if args.min_resources is not None:
        cfg.min_resources = args.min_resources
    if args.min_cluster_size is not None:
        cfg.min_cluster_size = args.min_cluster_size
    return cfg


def _filter_ignored(
    clusters: list[Cluster], cfg: Config
) -> tuple[list[Cluster], list[Cluster]]:
    """Split clusters into (kept, ignored)."""
    kept: list[Cluster] = []
    ignored: list[Cluster] = []
    for c in clusters:
        if cfg.matches_ignore(c.resources) is not None:
            ignored.append(c)
        else:
            kept.append(c)
    return kept, ignored


def cmd_scan(args: argparse.Namespace) -> int:
    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 2

    # Look for .parallax.toml relative to cwd (the convention of most
    # linters / formatters). Don't anchor on args.path — that may be a
    # subdir of the repo whose config lives at the root.
    cfg = load_config(args.config)
    cfg = _apply_overrides(args, cfg)

    extractor_names: list[str] = args.extractor or sorted(BUILTIN_EXTRACTORS)
    units: list[Unit] = []
    for name in extractor_names:
        cls = BUILTIN_EXTRACTORS[name]
        units.extend(cls().extract(args.path))

    clusters = group_by_resource_set(
        units,
        min_resources=cfg.min_resources,
        min_cluster_size=cfg.min_cluster_size,
    )
    kept, ignored = _filter_ignored(clusters, cfg)

    fmt = "json" if args.json else args.format
    if fmt == "text":
        output = render_text(
            kept,
            scanned_units=len(units),
            extractors=extractor_names,
            min_resources=cfg.min_resources,
            min_cluster_size=cfg.min_cluster_size,
        )
        if ignored:
            output += f"\n({len(ignored)} cluster(s) suppressed by ignore rules)\n"
    elif fmt == "json":
        output = render_json(kept, scanned_units=len(units))
    elif fmt == "html":
        output = render_html(
            kept,
            scanned_units=len(units),
            extractors=extractor_names,
            min_resources=cfg.min_resources,
            min_cluster_size=cfg.min_cluster_size,
        )
    elif fmt == "sarif":
        output = render_sarif(kept, scanned_units=len(units), extractors=extractor_names)
    else:  # pragma: no cover
        raise ValueError(f"unknown format: {fmt}")

    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")

    return _exit_code(kept, cfg, args.ci)


def _exit_code(kept: list[Cluster], cfg: Config, ci_mode: bool) -> int:
    if ci_mode:
        # CI gate: fail only when a cluster crosses the configured size.
        if cfg.max_cluster_size is None:
            return 0
        if any(c.size >= cfg.max_cluster_size for c in kept):
            return 1
        return 0
    # Default: any cluster is non-zero, no clusters is zero.
    return 0 if not kept else 1


def cmd_list_extractors(_: argparse.Namespace) -> int:
    for name, cls in sorted(BUILTIN_EXTRACTORS.items()):
        doc_first_line = (cls.__doc__ or "").strip().splitlines()[:1]
        summary = doc_first_line[0] if doc_first_line else ""
        print(f"{name:<14} {summary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_argparser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "list-extractors":
        return cmd_list_extractors(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
