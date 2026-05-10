"""Command-line interface for parallax."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import Unit, group_by_resource_set
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
        help=(
            "Which extractor to run. Repeat to combine multiple extractors. "
            "Default: all built-in extractors."
        ),
    )
    scan.add_argument(
        "--min-resources",
        type=int,
        default=2,
        help="Minimum distinct resources before a cluster is reported. Default 2.",
    )
    scan.add_argument(
        "--min-cluster-size",
        type=int,
        default=2,
        help="Minimum members in a cluster before it's reported. Default 2.",
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
    # Back-compat shortcut for `--format json`
    scan.add_argument(
        "--json",
        action="store_true",
        help="Shortcut for --format json.",
    )

    sub.add_parser("list-extractors", help="Print the extractors built into parallax.")

    return p


def cmd_scan(args: argparse.Namespace) -> int:
    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 2

    extractor_names: list[str] = args.extractor or sorted(BUILTIN_EXTRACTORS)
    units: list[Unit] = []
    for name in extractor_names:
        cls = BUILTIN_EXTRACTORS[name]
        units.extend(cls().extract(args.path))

    clusters = group_by_resource_set(
        units,
        min_resources=args.min_resources,
        min_cluster_size=args.min_cluster_size,
    )

    fmt = "json" if args.json else args.format
    if fmt == "text":
        output = render_text(
            clusters,
            scanned_units=len(units),
            extractors=extractor_names,
            min_resources=args.min_resources,
            min_cluster_size=args.min_cluster_size,
        )
    elif fmt == "json":
        output = render_json(clusters, scanned_units=len(units))
    elif fmt == "html":
        output = render_html(
            clusters,
            scanned_units=len(units),
            extractors=extractor_names,
            min_resources=args.min_resources,
            min_cluster_size=args.min_cluster_size,
        )
    elif fmt == "sarif":
        output = render_sarif(
            clusters, scanned_units=len(units), extractors=extractor_names
        )
    else:  # pragma: no cover — argparse choices guard this
        raise ValueError(f"unknown format: {fmt}")

    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")

    return 0 if not clusters else 1


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
