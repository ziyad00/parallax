"""parallax CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config, load_config
from .core import Cluster, Unit, group_by_resource_set
from .extractors import BUILTIN_EXTRACTORS
from .reporters import render_html, render_json, render_sarif, render_text
from .verify import verify_cluster


REPORTERS = {"text", "json", "html", "sarif"}


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="parallax",
        description="Find code that does the same logical job through different paths.",
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
        "--cross-file-only",
        action="store_true",
        help="Drop clusters whose units all live in one file.",
    )
    scan.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limit the report to the N highest-scoring clusters.",
    )
    scan.add_argument(
        "--fold-threshold",
        type=int,
        default=5,
        help="Collapse N+ methods of the same class into one row in text output. Set 0 to disable.",
    )
    scan.add_argument(
        "--ci",
        action="store_true",
        help="Exit non-zero only when a cluster meets ci.max_cluster_size from config.",
    )

    sub.add_parser("list-extractors", help="Print the extractors built into parallax.")

    verify = sub.add_parser(
        "verify",
        help="Read a cluster (JSON on stdin or --file) and run deeper analysis.",
    )
    verify.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Source root used to resolve unit locations. Default: cwd.",
    )
    verify.add_argument(
        "--file",
        type=Path,
        help="Read the cluster JSON from FILE instead of stdin.",
    )

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
        cross_file_only=args.cross_file_only,
    )
    kept, ignored = _filter_ignored(clusters, cfg)
    if args.top is not None and args.top >= 0:
        kept = kept[: args.top]

    fmt = "json" if args.json else args.format
    if fmt == "text":
        output = render_text(
            kept,
            scanned_units=len(units),
            extractors=extractor_names,
            min_resources=cfg.min_resources,
            min_cluster_size=cfg.min_cluster_size,
            fold_threshold=max(0, args.fold_threshold),
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
        if cfg.max_cluster_size is None:
            return 0
        if any(c.size >= cfg.max_cluster_size for c in kept):
            return 1
        return 0
    return 0 if not kept else 1


def cmd_verify(args: argparse.Namespace) -> int:
    raw = args.file.read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON: {e}", file=sys.stderr)
        return 2

    cluster: dict | None
    if isinstance(payload, dict) and "units" in payload:
        cluster = payload
    elif isinstance(payload, dict) and "clusters" in payload and payload["clusters"]:
        cluster = payload["clusters"][0]
    else:
        print(
            "error: expected a cluster dict (with 'units') or a scan payload "
            "(with 'clusters')",
            file=sys.stderr,
        )
        return 2

    results = verify_cluster(cluster, root=args.root)
    if not results:
        print("No applicable verifiers for this cluster.")
        return 0

    for r in results:
        print(
            f"verifier={r.verifier} "
            f"recommendation={r.recommendation.value} "
            f"mean_similarity={r.mean_similarity:.2f}"
        )
        for p in r.pairs:
            print(f"  {p.score:.2f}  {p.a_location}  ~  {p.b_location}")
    return 0


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
    if args.command == "verify":
        return cmd_verify(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
