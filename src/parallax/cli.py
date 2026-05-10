"""Command-line interface for parallax."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import Cluster, Unit, group_by_resource_set
from .extractors import BUILTIN_EXTRACTORS


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
    scan.add_argument(
        "path",
        type=Path,
        help="Root directory to scan.",
    )
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
        help=(
            "Minimum number of distinct resources before a cluster is reported. "
            "Higher = less noise. Default 2."
        ),
    )
    scan.add_argument(
        "--min-cluster-size",
        type=int,
        default=2,
        help="Minimum members in a cluster before it's reported. Default 2.",
    )
    scan.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON to stdout instead of text.",
    )

    sub.add_parser("list-extractors", help="Print the extractors built into parallax.")

    return p


def cmd_scan(args: argparse.Namespace) -> int:
    if not args.path.exists():
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 2

    extractor_names = args.extractor or sorted(BUILTIN_EXTRACTORS)
    units: list[Unit] = []
    for name in extractor_names:
        cls = BUILTIN_EXTRACTORS[name]
        units.extend(cls().extract(args.path))

    clusters = group_by_resource_set(
        units,
        min_resources=args.min_resources,
        min_cluster_size=args.min_cluster_size,
    )

    if args.json:
        _emit_json(units, clusters)
    else:
        _emit_text(args, units, clusters)
    return 0 if not clusters else 1


def _emit_text(
    args: argparse.Namespace, units: list[Unit], clusters: list[Cluster]
) -> None:
    print(
        f"Scanned {len(units)} units (extractors: "
        f"{', '.join(args.extractor or sorted(BUILTIN_EXTRACTORS))}). "
        f"Found {len(clusters)} clusters "
        f"(>= {args.min_resources} resources, >= {args.min_cluster_size} members).\n"
    )
    for c in clusters:
        resources = sorted(c.resources)
        print(f"--- {resources}  (+{c.size} units) ---")
        for u in c.units:
            lang = f"[{u.language}] " if u.language else ""
            print(f"    {lang}{u.location}::{u.name}")
        print()


def _emit_json(units: list[Unit], clusters: list[Cluster]) -> None:
    payload = {
        "scanned": len(units),
        "clusters": [
            {
                "resources": sorted(c.resources),
                "size": c.size,
                "units": [
                    {
                        "location": u.location,
                        "name": u.name,
                        "language": u.language,
                        "resources": sorted(u.resources),
                    }
                    for u in c.units
                ],
            }
            for c in clusters
        ],
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


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
