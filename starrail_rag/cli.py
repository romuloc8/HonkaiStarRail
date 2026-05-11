"""
Command-line interface for the Star Rail RAG extraction pipeline.

Usage examples
--------------
# Extract all 开拓主线 missions (default):
    python -m starrail_rag.cli

# Extract main + companion missions:
    python -m starrail_rag.cli --types Main Companion

# Extract a specific mission by ID:
    python -m starrail_rag.cli --mission-ids 1000101 1000201

# Specify data root and output directory:
    python -m starrail_rag.cli --data-root /path/to/StarRailData --output /path/to/output
"""

from __future__ import annotations

import argparse
import logging
import sys

from starrail_rag.pipeline import PipelineConfig, run_pipeline


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m starrail_rag.cli",
        description="Extract Star Rail story data into JSONL documents.",
    )
    p.add_argument(
        "--data-root",
        default="/workspace",
        metavar="PATH",
        help="Root of the StarRailData repository (default: /workspace)",
    )
    p.add_argument(
        "--output",
        default="/workspace/output",
        metavar="PATH",
        help="Output directory for JSONL files (default: /workspace/output)",
    )
    p.add_argument(
        "--locale",
        default="CHS",
        choices=["CHS", "EN", "JP", "KR"],
        help="TextMap locale (default: CHS)",
    )
    p.add_argument(
        "--extractors",
        nargs="+",
        default=["main_mission"],
        metavar="NAME",
        help="Extractor(s) to run (default: main_mission)",
    )
    p.add_argument(
        "--types",
        nargs="+",
        default=["Main"],
        metavar="TYPE",
        dest="mission_types",
        help="MainMission.Type values to include (default: Main)",
    )
    p.add_argument(
        "--mission-ids",
        nargs="+",
        type=int,
        default=None,
        metavar="ID",
        help="Restrict to specific MainMissionIDs (default: all)",
    )
    p.add_argument(
        "--wiki-categories",
        nargs="+",
        default=None,
        metavar="CATEGORY",
        dest="wiki_categories",
        help="wiki_category extractor: category names to scrape (default: all 4)",
    )
    p.add_argument(
        "--wiki-chapters",
        nargs="+",
        default=None,
        metavar="CHAPTER",
        help="Wiki extractor: limit to specific chapter names (default: all)",
    )
    p.add_argument(
        "--wiki-delay",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Wiki extractor: delay between requests in seconds (default: 1.0)",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    cfg = PipelineConfig(
        data_root=args.data_root,
        output_dir=args.output,
        locale=args.locale,
        extractors=args.extractors,
        mission_types=args.mission_types,
        mission_ids=args.mission_ids,
        wiki_chapters=args.wiki_chapters,
        wiki_categories=args.wiki_categories,
        wiki_request_delay=args.wiki_delay,
    )

    results = run_pipeline(cfg)

    # Summary table
    print("\n── Extraction Summary ──────────────────────────────")
    for r in results:
        print(
            f"  {r.extractor_name:<20}  "
            f"{r.non_empty_count:>4} docs  "
            f"({len(r.documents)} total)  "
            f"{r.elapsed_seconds:.1f}s"
        )
    print("────────────────────────────────────────────────────")
    print(f"Output: {cfg.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
