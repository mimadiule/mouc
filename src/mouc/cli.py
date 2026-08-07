"""Command-line interface for Mouc."""

from __future__ import annotations

import csv
import importlib
import importlib.util
import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import typer
from ruamel.yaml import YAML

from . import context, styling
from .backends import DocxBackend, MarkdownBackend
from .builtin_graph import register_builtin_clustering, resolve_cluster_value
from .document import DocumentGenerator
from .exceptions import MoucError
from .gantt import GanttScheduler, ScheduledTask, ScheduleResult
from .graph import GraphGenerator, GraphView
from .jira_cli import jira_app, write_feature_map
from .loader import load_feature_map
from .logger import setup_logger
from .models import Entity, FeatureMap
from .report_cli import report_app
from .scheduler import (
    AlgorithmConfig,
    AlgorithmType,
    ImplementationType,
    ScheduleAnnotations,
    SchedulingConfig,
    SchedulingResult,
    SchedulingService,
)
from .scheduler.lock import read_lock_file, write_lock_file
from .tag_filter import TagFilterSpec, parse_tag_options, select_entities, selection_is_empty
from .unified_config import GanttConfig, load_unified_config

app = typer.Typer(
    name="mouc",
    help="Mapping Outcomes User stories and Capabilities - A lightweight dependency tracking system",
    add_completion=False,
)


# Backwards compatibility wrapper for global state access
def get_config_path() -> Path | None:
    """Get the global config path."""
    return context.get_config_path()


def resolve_config_path(feature_map_path: Path | None = None) -> Path | None:
    """Resolve config path with priority: global --config > feature_map dir > cwd.

    Args:
        feature_map_path: Path to feature map YAML file. If provided, its parent
            directory is checked for mouc_config.yaml before falling back to cwd.

    Returns:
        Path to config file if found, None otherwise.
    """
    # Priority 1: Global --config option
    global_config = get_config_path()
    if global_config:
        return global_config

    # Priority 2: Config in feature map directory
    if feature_map_path:
        config_in_dir = feature_map_path.parent / "mouc_config.yaml"
        if config_in_dir.exists():
            return config_in_dir

    # Priority 3: Config in current working directory
    default = Path("mouc_config.yaml")
    if default.exists():
        return default

    return None


@app.callback()
def main_callback(
    verbose: Annotated[
        int,
        typer.Option(
            "--verbose",
            "-v",
            help="Verbosity level: 0=silent (default), 1=show changes, 2=show all checks, 3=debug",
            min=0,
            max=3,
        ),
    ] = 0,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to unified config file (default: mouc_config.yaml)",
        ),
    ] = None,
) -> None:
    """Global options for mouc commands."""
    setup_logger(verbose)
    context.set_config_path(config)


def _render_filtered_graph(
    feature_map: FeatureMap, styling_context: styling.StylingContext, spec: TagFilterSpec
) -> str:
    """Render --view filtered: drop negated entities up front, forward positive tags."""
    # TODO(unify-filtered-view-warning): this inline check diverges from _select_tag_entities.
    # Future special-cased views that bypass _apply_tag_filter must duplicate and maintain it.
    # Emit empty-match warning when no entities survive both positive-tag match and negation.
    if spec.include and not any(
        (set(e.tags) & spec.include) and not (set(e.tags) & spec.exclude)
        for e in feature_map.entities
    ):
        typer.echo("warning: --tags matched no entities", err=True)

    excl = spec.exclude
    negation_ids = (
        {e.id for e in feature_map.entities if not (set(e.tags) & excl)} if excl else None
    )
    with _install_ephemeral_filter(negation_ids):
        generator = GraphGenerator(feature_map, styling_context)
        return generator.generate(GraphView.FILTERED, tags=list(spec.include) or None)


def _has_cluster_value(entity: Entity, segments: list[str]) -> bool:
    """Whether the --cluster-by path resolves to anything for this entity.

    An unusable value counts as a value: the path does resolve, so the no-match
    warning does not apply, and generation reports the error if and only if the
    entity survives filtering.
    """
    try:
        return resolve_cluster_value(entity, segments) is not None
    except ValueError:
        return True


def _warn_unmatched_cluster_path(feature_map: FeatureMap, segments: list[str]) -> None:
    """Warn on stderr when no entity resolves a value for the --cluster-by path."""
    if not any(_has_cluster_value(e, segments) for e in feature_map.entities):
        typer.echo("warning: --cluster-by matched no entities", err=True)


@app.command()
def graph(  # noqa: PLR0913 - CLI command needs multiple options
    file: Annotated[Path, typer.Argument(help="Path to the feature map YAML file")] = Path(
        "feature_map.yaml"
    ),
    *,
    view: Annotated[
        GraphView, typer.Option("--view", help="Type of graph to generate")
    ] = GraphView.ALL,
    target: Annotated[
        str | None, typer.Option("--target", "-t", help="Target for critical path view")
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tags",
            help=(
                "Filter to entities tagged with any of TAGS (comma-separated or repeated). "
                "Prefix `!` to exclude. Includes all transitive upstream and downstream "
                "dependencies. Combine with --style-tags for style-function activation."
            ),
        ),
    ] = None,
    tags_direction: Annotated[
        str,
        typer.Option(
            "--tags-direction",
            help="Limit closure direction: both | up | down (default: both)",
        ),
    ] = "both",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file path")] = None,
    style_module: Annotated[
        str | None,
        typer.Option("--style-module", help="Python module path for styling functions"),
    ] = None,
    style_file: Annotated[
        Path | None,
        typer.Option("--style-file", help="Python file path for styling functions"),
    ] = None,
    style_tags: Annotated[
        str | None,
        typer.Option(
            "--style-tags",
            help="Comma-separated tags to enable styling functions (merged with config)",
        ),
    ] = None,
    cluster_by: Annotated[
        str | None,
        typer.Option(
            "--cluster-by",
            help=(
                "Group nodes into subgraph clusters by a dotted entity field path "
                "(e.g. meta.repo). Shortcut for a built-in @group_tasks function; a "
                "user grouping function overrides it. List values cluster by their "
                "first entry; entities without a value render outside all clusters."
            ),
        ),
    ] = None,
) -> None:
    """Generate dependency graphs in DOT format."""
    # Validate arguments
    if view == GraphView.CRITICAL_PATH and not target:
        typer.echo("Error: Critical path view requires --target", err=True)
        raise typer.Exit(1)

    if view == GraphView.FILTERED and not tags:
        typer.echo("Error: Filtered view requires --tags", err=True)
        raise typer.Exit(1)

    if style_module and style_file:
        typer.echo("Error: Cannot specify both --style-module and --style-file", err=True)
        raise typer.Exit(1)

    if cluster_by and view == GraphView.TIMELINE:
        typer.echo("Error: --cluster-by cannot be combined with --view timeline", err=True)
        raise typer.Exit(1)

    # Parse tag filter spec; for --view filtered, reject empty or negation-only specs.
    spec = _resolve_tag_filter(tags, tags_direction)
    if view == GraphView.FILTERED and len(spec.include) == 0:
        typer.echo("Error: --view filtered requires at least one positive --tags token", err=True)
        raise typer.Exit(1)

    # Load styling module if specified
    if style_module or style_file:
        _load_styling(style_module, style_file)

    # Load the feature map
    feature_map = load_feature_map(file)

    # Collect style tags from CLI and config
    active_style_tags = _collect_style_tags(style_tags, file)

    # Create styling context with tags
    styling_context = styling.create_styling_context(
        feature_map, output_format="graph", style_tags=active_style_tags
    )

    try:
        clustering = register_builtin_clustering(cluster_by)
        # Skip the scan when a user grouping function outranks the built-in: the flag
        # has no effect on the output, so neither its warning nor its errors apply.
        if clustering and styling.active_grouping_func(styling_context) is clustering.func:
            _warn_unmatched_cluster_path(feature_map, clustering.segments)
        if view == GraphView.FILTERED and not spec.is_empty:
            dot_output = _render_filtered_graph(feature_map, styling_context, spec)
        else:
            with _apply_tag_filter(feature_map, spec):
                generator = GraphGenerator(feature_map, styling_context)
                dot_output = generator.generate(view, target=target, tags=tags)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e

    # Output the result
    if output:
        output.write_text(dot_output, encoding="utf-8")
        typer.echo(f"Graph written to {output}")
    else:
        typer.echo(dot_output)


@app.command()
def doc(  # noqa: PLR0913, PLR0912, PLR0915 - CLI command needs multiple options and has complex logic
    file: Annotated[Path, typer.Argument(help="Path to the feature map YAML file")] = Path(
        "feature_map.yaml"
    ),
    *,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file path")] = None,
    format: Annotated[  # noqa: A002 - 'format' is appropriate name for CLI option
        str,
        typer.Option("--format", "-f", help="Output format (markdown or docx)"),
    ] = "markdown",
    schedule: Annotated[
        bool,
        typer.Option(
            "--schedule",
            help="Run scheduler and populate schedule annotations for use in styling functions",
        ),
    ] = False,
    current_date: Annotated[
        str | None,
        typer.Option(
            "--current-date",
            help="Current/as-of date for scheduling (YYYY-MM-DD). Only used with --schedule",
        ),
    ] = None,
    lock_file: Annotated[
        Path | None,
        typer.Option(
            "--lock-file",
            help="Use pre-computed schedule from lock file",
        ),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tags",
            help=(
                "Filter to entities tagged with any of TAGS (comma-separated or repeated). "
                "Prefix `!` to exclude. Includes all transitive upstream and downstream "
                "dependencies. Combine with --style-tags for style-function activation."
            ),
        ),
    ] = None,
    tags_direction: Annotated[
        str,
        typer.Option(
            "--tags-direction",
            help="Limit closure direction: both | up | down (default: both)",
        ),
    ] = "both",
    style_module: Annotated[
        str | None,
        typer.Option("--style-module", help="Python module path for styling functions"),
    ] = None,
    style_file: Annotated[
        Path | None,
        typer.Option("--style-file", help="Python file path for styling functions"),
    ] = None,
    style_tags: Annotated[
        str | None,
        typer.Option(
            "--style-tags",
            help="Comma-separated tags to enable styling functions (merged with config)",
        ),
    ] = None,
) -> None:
    """Generate documentation in Markdown or DOCX format."""
    # Validate format option
    if format not in ("markdown", "docx"):
        typer.echo(
            f"Error: Invalid format '{format}'. Must be 'markdown' or 'docx'.",
            err=True,
        )
        raise typer.Exit(1)

    if style_module and style_file:
        typer.echo("Error: Cannot specify both --style-module and --style-file", err=True)
        raise typer.Exit(1)

    # Load styling module if specified
    if style_module or style_file:
        _load_styling(style_module, style_file)

    # Load the feature map
    feature_map = load_feature_map(file)

    # Load unified config if available
    unified_config = None
    config_path = resolve_config_path(file)
    if config_path:
        unified_config = load_unified_config(config_path)

    # Load schedule lock file if specified
    schedule_lock = None
    if lock_file:
        if not lock_file.exists():
            typer.echo(f"Error: Lock file not found: {lock_file}", err=True)
            raise typer.Exit(1)
        try:
            schedule_lock = read_lock_file(lock_file)
        except ValueError as e:
            typer.echo(f"Error reading lock file: {e}", err=True)
            raise typer.Exit(1) from None

    # Optionally run scheduler to populate annotations
    if schedule or lock_file:
        # Parse current date if provided
        parsed_current_date: date | None = None
        if current_date:
            try:
                parsed_current_date = date.fromisoformat(current_date)
            except ValueError as e:
                typer.echo(
                    f"Error: Invalid date format '{current_date}'. Use YYYY-MM-DD",
                    err=True,
                )
                raise typer.Exit(1) from e

        # Get resource config from unified config if available
        resource_config = unified_config.resources if unified_config else None

        # Get scheduler config from unified config if available
        scheduler_config = unified_config.scheduler if unified_config else None

        # Get global DNS periods from unified config if available
        global_dns_periods = unified_config.global_dns_periods if unified_config else None

        # Run scheduling and populate annotations
        service = SchedulingService(
            feature_map,
            parsed_current_date,
            resource_config,
            scheduler_config,
            global_dns_periods,
            schedule_lock=schedule_lock,
        )
        service.populate_feature_map_annotations()

    # Collect style tags from CLI and config
    active_style_tags = _collect_style_tags(style_tags, file)

    spec = _resolve_tag_filter(tags, tags_direction)
    with _apply_tag_filter(feature_map, spec):
        # Generate the documentation
        styling_context = styling.create_styling_context(
            feature_map, output_format=format, style_tags=active_style_tags
        )

        # Select backend and config based on format
        if format == "docx":
            doc_config = unified_config.docx if unified_config else None
            table_style = doc_config.table_style if doc_config else "Table Grid"
            backend = DocxBackend(feature_map, styling_context, table_style)
        else:
            backend = MarkdownBackend(feature_map, styling_context)
            doc_config = unified_config.markdown if unified_config else None

        generator = DocumentGenerator(feature_map, backend, doc_config, unified_config)
        doc_output = generator.generate()

    # Output the result
    if output:
        if isinstance(doc_output, bytes):
            output.write_bytes(doc_output)
        else:
            output.write_text(doc_output, encoding="utf-8")
        typer.echo(f"Documentation written to {output}")
    elif isinstance(doc_output, bytes):
        typer.echo(doc_output.decode("utf-8"))
    else:
        typer.echo(doc_output)


def _validate_gantt_params(
    group_by: str | None, sort_by: str | None, vertical_dividers: str | None
) -> None:
    """Validate gantt command parameters."""
    if group_by and group_by not in ("none", "type", "resource", "timeframe"):
        typer.echo(
            f"Error: Invalid group-by value '{group_by}'. "
            "Must be 'none', 'type', 'resource', or 'timeframe'.",
            err=True,
        )
        raise typer.Exit(1) from None

    if sort_by and sort_by not in ("start", "end", "deadline", "name", "priority", "yaml_order"):
        typer.echo(
            f"Error: Invalid sort-by value '{sort_by}'. "
            "Must be 'start', 'end', 'deadline', 'name', 'priority', or 'yaml_order'.",
            err=True,
        )
        raise typer.Exit(1) from None

    if vertical_dividers and vertical_dividers not in ("quarter", "halfyear", "year"):
        typer.echo(
            f"Error: Invalid vertical-dividers value '{vertical_dividers}'. "
            "Must be 'quarter', 'halfyear', or 'year'.",
            err=True,
        )
        raise typer.Exit(1) from None


def _parse_date_option(date_str: str | None, option_name: str) -> date | None:
    """Parse a date string from CLI option.

    Args:
        date_str: Date string in YYYY-MM-DD format or None
        option_name: Name of the option for error messages

    Returns:
        Parsed date object or None if date_str is None
    """
    if date_str is None:
        return None

    try:
        return date.fromisoformat(date_str)
    except ValueError:
        typer.echo(
            f"Error: Invalid date format '{date_str}'. Use YYYY-MM-DD format.",
            err=True,
        )
        raise typer.Exit(1) from None


def _resolve_gantt_config_path(
    resources: Path | None, feature_map_path: Path | None = None
) -> Path | None:
    """Resolve resource config path with priority: --resources > global --config > feature_map dir > default."""
    if resources:
        return resources
    return resolve_config_path(feature_map_path)


def _format_gantt_output(mermaid_output: str, output_path: Path | None) -> None:
    """Output or write Gantt chart result."""
    if output_path:
        # Wrap in markdown code fence if output is a .md file
        if output_path.suffix.lower() == ".md":
            output_content = f"```mermaid\n{mermaid_output}\n```\n"
        else:
            output_content = mermaid_output
        output_path.write_text(output_content, encoding="utf-8")
        typer.echo(f"Gantt chart written to {output_path}")
    else:
        typer.echo(mermaid_output)


@app.command()
def gantt(  # noqa: PLR0913, PLR0912, PLR0915 - CLI command needs multiple options
    file: Annotated[Path, typer.Argument(help="Path to the feature map YAML file")] = Path(
        "feature_map.yaml"
    ),
    *,
    start_date: Annotated[
        str | None,
        typer.Option(
            "--start-date",
            "-s",
            help="Chart start date (left edge of visualization, YYYY-MM-DD). "
            "Defaults to min(first fixed task date, current date)",
        ),
    ] = None,
    current_date: Annotated[
        str | None,
        typer.Option(
            "--current-date",
            "-c",
            help="Current/as-of date for scheduling (YYYY-MM-DD). Defaults to today",
        ),
    ] = None,
    title: Annotated[str, typer.Option("--title", "-t", help="Chart title")] = "Project Schedule",
    group_by: Annotated[
        str | None,
        typer.Option(
            "--group-by",
            help="Group tasks by: 'none', 'type', 'resource', or 'timeframe'",
        ),
    ] = None,
    sort_by: Annotated[
        str | None,
        typer.Option(
            "--sort-by",
            help="Sort tasks by: 'start', 'end', 'deadline', 'name', 'priority', or 'yaml_order'",
        ),
    ] = None,
    tick_interval: Annotated[
        str | None,
        typer.Option(
            "--tick-interval",
            help="Mermaid tickInterval for x-axis (e.g., '1week', '1month', '3month' for quarters)",
        ),
    ] = None,
    axis_format: Annotated[
        str | None,
        typer.Option(
            "--axis-format",
            help="Mermaid axisFormat for date display (e.g., '%%Y-%%m-%%d', '%%b %%Y')",
        ),
    ] = None,
    vertical_dividers: Annotated[
        str | None,
        typer.Option(
            "--vertical-dividers",
            help="Add vertical dividers at intervals: 'quarter', 'halfyear', or 'year'",
        ),
    ] = None,
    compact: Annotated[
        bool,
        typer.Option(
            "--compact",
            help="Use compact display mode to show multiple tasks in same row when possible",
        ),
    ] = False,
    resources: Annotated[
        Path | None,
        typer.Option(
            "--resources",
            "-r",
            help="[DEPRECATED] Use --config instead. Path to resources.yaml file for automatic resource assignment",
        ),
    ] = None,
    markdown_base_url: Annotated[
        str | None,
        typer.Option(
            "--markdown-base-url",
            help="Base URL for markdown links (e.g., './feature_map.md' or 'https://github.com/user/repo/blob/main/feature_map.md')",
        ),
    ] = None,
    style_module: Annotated[
        str | None,
        typer.Option("--style-module", help="Python module path for styling functions"),
    ] = None,
    style_file: Annotated[
        Path | None,
        typer.Option("--style-file", help="Python file path for styling functions"),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tags",
            help=(
                "Filter to entities tagged with any of TAGS (comma-separated or repeated). "
                "Prefix `!` to exclude. Includes all transitive upstream and downstream "
                "dependencies. Combine with --style-tags for style-function activation."
            ),
        ),
    ] = None,
    tags_direction: Annotated[
        str,
        typer.Option(
            "--tags-direction",
            help="Limit closure direction: both | up | down (default: both)",
        ),
    ] = "both",
    style_tags: Annotated[
        str | None,
        typer.Option(
            "--style-tags",
            help="Comma-separated tags to enable styling functions (merged with config)",
        ),
    ] = None,
    algorithm: Annotated[
        str | None,
        typer.Option(
            "--algorithm",
            "-a",
            help="Scheduling algorithm to use. Overrides config. Available: 'parallel_sgs'",
        ),
    ] = None,
    rust: Annotated[
        bool,
        typer.Option("--rust", help="Use Rust scheduler implementation (faster)"),
    ] = False,
    lock_file: Annotated[
        Path | None,
        typer.Option(
            "--lock-file", help="Use pre-computed schedule from lock file (skips scheduling)"
        ),
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output file path")] = None,
) -> None:
    """Generate Gantt chart in Mermaid format."""
    if style_module and style_file:
        typer.echo("Error: Cannot specify both --style-module and --style-file", err=True)
        raise typer.Exit(1)

    # Load styling module if specified
    if style_module or style_file:
        _load_styling(style_module, style_file)

    # Validate parameters
    _validate_gantt_params(group_by, sort_by, vertical_dividers)

    # Parse dates
    parsed_start_date = _parse_date_option(start_date, "start-date")
    parsed_current_date = _parse_date_option(current_date, "current-date")

    # Load the feature map
    feature_map = load_feature_map(file)

    # Resolve config path and load config
    resource_config_path = _resolve_gantt_config_path(resources, file)

    # Load gantt config and allow CLI override
    gantt_config = None
    gantt_config_markdown_url = None
    scheduler_config = None
    if resource_config_path:
        with suppress(FileNotFoundError, ValueError):
            unified_config = load_unified_config(resource_config_path)
            gantt_config = unified_config.gantt or GanttConfig()
            gantt_config_markdown_url = gantt_config.markdown_base_url
            scheduler_config = unified_config.scheduler

    # If no config loaded, create default
    if gantt_config is None:
        gantt_config = GanttConfig()

    # CLI overrides config
    if group_by is not None:
        gantt_config.group_by = group_by
    if sort_by is not None:
        gantt_config.sort_by = sort_by

    # Override algorithm if specified on CLI
    if algorithm:
        try:
            algorithm_type = AlgorithmType(algorithm)
        except ValueError:
            typer.echo(
                f"Error: Invalid algorithm '{algorithm}'. "
                f"Available: {', '.join(a.value for a in AlgorithmType)}",
                err=True,
            )
            raise typer.Exit(1) from None
        if scheduler_config is None:
            scheduler_config = SchedulingConfig()
        scheduler_config.algorithm = AlgorithmConfig(type=algorithm_type)

    # Override implementation if --rust flag is passed
    if rust:
        if scheduler_config is None:
            scheduler_config = SchedulingConfig()
        scheduler_config.implementation = ImplementationType.RUST

    final_markdown_url = markdown_base_url or gantt_config_markdown_url

    # Collect style tags from CLI and config
    active_style_tags = _collect_style_tags(style_tags, file)

    # Parse tag filter; scheduling runs over the full entity set (requirement A3).
    # The ephemeral filter is installed after scheduling.
    spec = _resolve_tag_filter(tags, tags_direction)

    # Create GanttScheduler (needed for Mermaid generation regardless of scheduling mode)
    scheduler = GanttScheduler(
        feature_map,
        start_date=parsed_start_date,
        current_date=parsed_current_date,
        resource_config_path=resource_config_path,
        scheduler_config=scheduler_config,
        gantt_config=gantt_config,
        style_tags=active_style_tags,
    )

    if lock_file:
        # Load pre-computed schedule from lock file (skip scheduling)
        schedule_lock = read_lock_file(lock_file)
        tasks: list[ScheduledTask] = []
        annotations: dict[str, ScheduleAnnotations] = {}
        for task_id, lock in schedule_lock.locks.items():
            tasks.append(
                ScheduledTask(
                    entity_id=task_id,
                    start_date=lock.start_date,
                    end_date=lock.end_date,
                    duration_days=(lock.end_date - lock.start_date).days,
                    resources=[r[0] for r in lock.resources],
                )
            )
            annotations[task_id] = ScheduleAnnotations(
                estimated_start=lock.start_date,
                estimated_end=lock.end_date,
                computed_deadline=None,
                computed_priority=None,
                deadline_violated=False,
                resource_assignments=lock.resources,
                resources_were_computed=lock.resources_were_computed,
                was_fixed=lock.was_fixed,
            )
        result = ScheduleResult(tasks=tasks)
        scheduler._scheduling_annotations = annotations  # pyright: ignore[reportPrivateUsage]
    else:
        result = scheduler.schedule()

    # Install ephemeral tag filter after scheduling so rendering is restricted
    # but scheduled dates reflect the full entity graph.
    with _apply_tag_filter(feature_map, spec):
        # Create anchor function for markdown links if needed
        anchor_fn = None
        if final_markdown_url:
            styling_context = styling.create_styling_context(
                feature_map, output_format="gantt", style_tags=active_style_tags
            )
            backend = MarkdownBackend(feature_map, styling_context)
            anchor_fn = backend.make_anchor

        # Generate Mermaid chart
        mermaid_output = scheduler.generate_mermaid(
            result,
            title=title,
            tick_interval=tick_interval,
            axis_format=axis_format,
            vertical_dividers=vertical_dividers,
            compact=compact,
            markdown_base_url=final_markdown_url,
            anchor_fn=anchor_fn,
        )

    # Output the result
    _format_gantt_output(mermaid_output, output)

    # Show warnings if any
    if result.warnings:
        typer.echo("\nWarnings:", err=True)
        for warning in result.warnings:
            typer.echo(f"  - {warning}", err=True)


def _annotate_feature_map(
    feature_map: FeatureMap,
    result: SchedulingResult,
    file: Path,
    active_style_tags: set[str] | None = None,
) -> None:
    """Write schedule annotations back to feature map YAML file."""
    annotate_context = styling.create_styling_context(
        feature_map, output_format="schedule", style_tags=active_style_tags or set()
    )
    annotate_entities = cast(
        list[Entity], styling.apply_entity_filters(feature_map.entities, annotate_context)
    )
    for entity in annotate_entities:
        if entity.id in result.annotations:
            annot = result.annotations[entity.id]
            if annot.estimated_start:
                entity.meta["estimated_start"] = annot.estimated_start.isoformat()
            if annot.estimated_end:
                entity.meta["estimated_end"] = annot.estimated_end.isoformat()

    write_feature_map(file, feature_map)
    typer.echo(f"Annotations written to {file}")


def _display_schedule_results(
    feature_map: FeatureMap,
    result: SchedulingResult,
    active_style_tags: set[str] | None = None,
) -> None:
    """Display schedule results to stdout."""
    typer.echo("Schedule Results")
    typer.echo("=" * 80)
    typer.echo("")

    display_context = styling.create_styling_context(
        feature_map, output_format="schedule", style_tags=active_style_tags or set()
    )
    display_entities = cast(
        list[Entity], styling.apply_entity_filters(feature_map.entities, display_context)
    )

    for entity in display_entities:
        if entity.id not in result.annotations:
            continue

        annot = result.annotations[entity.id]
        typer.echo(f"{entity.name} ({entity.id})")
        typer.echo(f"  Estimated Start:  {annot.estimated_start}")
        typer.echo(f"  Estimated End:    {annot.estimated_end}")
        if annot.computed_deadline:
            typer.echo(f"  Computed Deadline: {annot.computed_deadline}")
        if annot.deadline_violated:
            typer.echo("  ⚠️  DEADLINE VIOLATED")
        typer.echo(f"  Resources: {', '.join(f'{r}:{a}' for r, a in annot.resource_assignments)}")
        if annot.resources_were_computed:
            typer.echo("  (resources auto-assigned)")
        if annot.was_fixed:
            typer.echo("  (fixed dates, not scheduled)")
        typer.echo("")


def _export_schedule_csv(
    entities: Sequence[Entity],
    result: SchedulingResult,
    output_path: Path,
    default_priority: int,
) -> None:
    """Export schedule results to CSV for scenario comparison."""
    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["task_id", "task_name", "priority", "deadline", "completion_date"])

        for entity in entities:
            if entity.id not in result.annotations:
                continue

            annot = result.annotations[entity.id]
            priority = entity.meta.get("priority", default_priority)
            deadline = entity.meta.get("end_before", "")
            completion_date = annot.estimated_end.isoformat() if annot.estimated_end else ""

            writer.writerow([entity.id, entity.name, priority, deadline, completion_date])


@app.command()
def schedule(  # noqa: PLR0913, PLR0912, PLR0915 - CLI command needs multiple options
    file: Annotated[Path, typer.Argument(help="Path to the feature map YAML file")] = Path(
        "feature_map.yaml"
    ),
    current_date: Annotated[
        str | None,
        typer.Option(
            "--current-date",
            "-c",
            help="Current/as-of date for scheduling (YYYY-MM-DD). Defaults to today",
        ),
    ] = None,
    algorithm: Annotated[
        str | None,
        typer.Option(
            "--algorithm",
            "-a",
            help="Scheduling algorithm to use. Overrides config. Available: 'parallel_sgs'",
        ),
    ] = None,
    rust: Annotated[
        bool,
        typer.Option("--rust", help="Use Rust scheduler implementation (faster)"),
    ] = False,
    annotate_yaml: Annotated[
        bool,
        typer.Option(
            "--annotate-yaml",
            help="Write estimated_start/estimated_end back to YAML file",
        ),
    ] = False,
    output_csv: Annotated[
        Path | None,
        typer.Option(
            "--output-csv",
            help="Export schedule results to CSV file for scenario comparison. Always reflects the full scheduled set regardless of --tags.",
        ),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tags",
            help=(
                "Filter displayed entities to those tagged with any of TAGS "
                "(comma-separated or repeated). Prefix `!` to exclude. Includes all transitive "
                "upstream and downstream dependencies. Scheduling considers the full entity graph; "
                "only output is restricted. Lock files always reflect the full schedule. "
                "Combine with --style-tags for style-function activation."
            ),
        ),
    ] = None,
    tags_direction: Annotated[
        str,
        typer.Option(
            "--tags-direction",
            help="Limit closure direction: both | up | down (default: both)",
        ),
    ] = "both",
    style_tags: Annotated[
        str | None,
        typer.Option(
            "--style-tags",
            help="Comma-separated tags to filter entities (merged with config)",
        ),
    ] = None,
    style_module: Annotated[
        str | None,
        typer.Option("--style-module", help="Python module path for styling/filter functions"),
    ] = None,
    style_file: Annotated[
        Path | None,
        typer.Option("--style-file", help="Python file path for styling/filter functions"),
    ] = None,
    lock_file: Annotated[
        Path | None,
        typer.Option(
            "--lock-file",
            help="Load fixed dates/resources from a previous scheduling run",
        ),
    ] = None,
    output_lock: Annotated[
        Path | None,
        typer.Option(
            "--output-lock",
            help="Export scheduled dates/resources to lock file for phased scheduling",
        ),
    ] = None,
) -> None:
    """Run scheduling algorithm and display or persist results."""
    if tags and annotate_yaml:
        typer.echo(
            "Error: --tags and --annotate-yaml cannot be combined; "
            "--annotate-yaml writes only the filtered entity subset, leaving other "
            "entities with stale annotations. Omit --tags to annotate all entities.",
            err=True,
        )
        raise typer.Exit(1)

    # Parse current date if provided
    parsed_current_date = _parse_date_option(current_date, "current-date")

    # Validate and load styling module/file if specified (before filtering)
    if style_module and style_file:
        typer.echo("Error: Cannot specify both --style-module and --style-file", err=True)
        raise typer.Exit(1)
    if style_module or style_file:
        _load_styling(style_module, style_file)

    # Load the feature map
    feature_map = load_feature_map(file)

    # Compute selected_ids from full feature map before any style-tag filter.
    spec = _resolve_tag_filter(tags, tags_direction)
    selected_ids = _select_tag_entities(feature_map, spec)

    # Load schedule lock file if specified
    schedule_lock = None
    if lock_file:
        if not lock_file.exists():
            typer.echo(f"Error: Lock file not found: {lock_file}", err=True)
            raise typer.Exit(1)
        try:
            schedule_lock = read_lock_file(lock_file)
            typer.echo(f"Loaded {len(schedule_lock.locks)} task locks from {lock_file}")
        except ValueError as e:
            typer.echo(f"Error reading lock file: {e}", err=True)
            raise typer.Exit(1) from None

    # Load resource and scheduler config if available
    config_path = resolve_config_path(file)
    resource_config = None
    scheduler_config = None
    global_dns_periods = None
    if config_path:
        unified = load_unified_config(config_path)
        resource_config = unified.resources
        scheduler_config = unified.scheduler
        global_dns_periods = unified.global_dns_periods

    # Override algorithm if specified on CLI
    if algorithm:
        try:
            algorithm_type = AlgorithmType(algorithm)
        except ValueError:
            typer.echo(
                f"Error: Invalid algorithm '{algorithm}'. "
                f"Available: {', '.join(a.value for a in AlgorithmType)}",
                err=True,
            )
            raise typer.Exit(1) from None
        if scheduler_config is None:
            scheduler_config = SchedulingConfig()
        scheduler_config.algorithm = AlgorithmConfig(type=algorithm_type)

    # Override implementation if --rust flag is passed
    if rust:
        if scheduler_config is None:
            scheduler_config = SchedulingConfig()
        scheduler_config.implementation = ImplementationType.RUST

    # --style-tags pre-schedule filter (locked entities always included).
    active_style_tags = _collect_style_tags(style_tags, file)
    if active_style_tags:
        styling_context = styling.create_styling_context(
            feature_map, output_format="schedule", style_tags=active_style_tags
        )
        filtered_entities = styling.apply_entity_filters(feature_map.entities, styling_context)
        # Add back any locked entities that were filtered out
        if schedule_lock:
            filtered_ids = {e.id for e in filtered_entities}
            for entity in feature_map.entities:
                if entity.id in schedule_lock.locks and entity.id not in filtered_ids:
                    filtered_entities.append(entity)
        # Create filtered feature map for scheduling
        feature_map = replace(feature_map, entities=filtered_entities)

    # Run scheduling service.
    service = SchedulingService(
        feature_map,
        parsed_current_date,
        resource_config,
        scheduler_config,
        global_dns_periods,
        schedule_lock=schedule_lock,
    )
    result = service.schedule()

    # Install post-schedule --tags filter (display only).
    with _install_ephemeral_filter(selected_ids):
        # Display / CSV / annotate paths.
        if output_csv:
            # Apply CSV-specific output filters
            csv_context = styling.create_styling_context(
                feature_map, output_format="csv", style_tags=active_style_tags
            )
            csv_entities = cast(
                list[Entity], styling.apply_entity_filters(feature_map.entities, csv_context)
            )
            default_priority = (
                scheduler_config.default_priority
                if scheduler_config
                else SchedulingConfig().default_priority
            )
            _export_schedule_csv(csv_entities, result, output_csv, default_priority)
            typer.echo(f"Schedule exported to {output_csv}")
        elif annotate_yaml:
            _annotate_feature_map(feature_map, result, file, active_style_tags)
        else:
            _display_schedule_results(feature_map, result, active_style_tags)

    # Lock files always reflect the full schedule (not the filtered set).
    if output_lock:
        write_lock_file(output_lock, result)
        typer.echo(f"Lock file written to {output_lock}")

    # Display warnings
    if result.warnings:
        typer.echo("\nWarnings:", err=True)
        for warning in result.warnings:
            typer.echo(f"  - {warning}", err=True)


@app.command()
def compare(
    baseline: Annotated[Path, typer.Argument(help="Baseline CSV file from schedule --output-csv")],
    scenarios: Annotated[
        list[Path], typer.Argument(help="One or more scenario CSV files to compare")
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file (default: stdout)"),
    ] = None,
) -> None:
    """Compare schedule scenarios against a baseline.

    Takes CSV files exported from 'schedule --output-csv' and produces a combined
    comparison showing completion dates and deltas for each scenario.
    """
    # Read baseline
    baseline_data: dict[str, dict[str, str]] = {}
    with baseline.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            baseline_data[row["task_id"]] = row

    # Read scenarios
    scenario_names: list[str] = []
    scenario_data: list[dict[str, dict[str, str]]] = []
    for scenario_path in scenarios:
        name = scenario_path.stem  # filename without extension
        scenario_names.append(name)
        data: dict[str, dict[str, str]] = {}
        with scenario_path.open(newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                data[row["task_id"]] = row
        scenario_data.append(data)

    # Collect all task IDs (baseline union scenarios)
    all_task_ids = set(baseline_data.keys())
    for data in scenario_data:
        all_task_ids.update(data.keys())

    # Build header
    header = ["task_id", "task_name", "priority", "deadline", "completion_baseline"]
    for name in scenario_names:
        header.append(f"completion_{name}")
        header.append(f"delta_{name}")

    # Build rows
    rows: list[list[str]] = []
    for task_id in sorted(all_task_ids):
        baseline_row = baseline_data.get(task_id, {})
        task_name = baseline_row.get("task_name", "")
        priority = baseline_row.get("priority", "")
        deadline = baseline_row.get("deadline", "")
        baseline_completion = baseline_row.get("completion_date", "")

        row = [task_id, task_name, priority, deadline, baseline_completion]

        for i in range(len(scenario_names)):
            scenario_row = scenario_data[i].get(task_id, {})
            scenario_completion = scenario_row.get("completion_date", "")
            row.append(scenario_completion)

            # Compute delta in days
            delta = ""
            if baseline_completion and scenario_completion:
                try:
                    base_date = date.fromisoformat(baseline_completion)
                    scen_date = date.fromisoformat(scenario_completion)
                    delta = str((scen_date - base_date).days)
                except ValueError:
                    pass
            row.append(delta)

        rows.append(row)

    # Write output
    out_file = output.open("w", newline="") if output else sys.stdout
    try:
        writer = csv.writer(out_file)
        writer.writerow(header)
        writer.writerows(rows)
    finally:
        if output:
            out_file.close()

    if output:
        typer.echo(f"Comparison written to {output}")


@app.command()
def status(
    target: Annotated[str, typer.Argument(help="Outcome ID to check status for")],
    file: Annotated[
        Path, typer.Option("--file", "-f", help="Path to the feature map YAML file")
    ] = Path("feature_map.yaml"),
) -> None:
    """Show status of an outcome and its dependencies."""
    typer.echo(f"Status query for '{target}' not yet implemented", err=True)
    raise typer.Exit(1)


@app.command()
def audit(
    check: Annotated[str, typer.Argument(help="Type of audit check (e.g., 'no-design-doc')")],
    tags: Annotated[list[str] | None, typer.Option("--tags", help="Filter by tags")] = None,
    file: Annotated[
        Path, typer.Option("--file", "-f", help="Path to the feature map YAML file")
    ] = Path("feature_map.yaml"),
) -> None:
    """Run audit checks on the feature map."""
    typer.echo(f"Audit check '{check}' not yet implemented", err=True)
    raise typer.Exit(1)


@app.command(name="convert-format")
def convert_format(
    file: Annotated[
        Path, typer.Argument(help="Path to the old-format feature map YAML file")
    ] = Path("feature_map.yaml"),
) -> None:
    """Convert old 3-section format to unified entities format.

    Outputs converted YAML to stdout. Use redirection to save:

        mouc convert-format feature_map.yaml > feature_map_new.yaml
    """
    if not file.exists():
        typer.echo(f"Error: File not found: {file}", err=True)
        raise typer.Exit(1)

    yaml_rt = YAML()
    yaml_rt.preserve_quotes = True  # type: ignore[assignment]

    with file.open(encoding="utf-8") as f:
        data = yaml_rt.load(f)  # type: ignore[no-untyped-call]

    if not isinstance(data, dict):
        typer.echo("Error: YAML must contain a dictionary at the root level", err=True)
        raise typer.Exit(1)

    # Check if already in new format
    if "entities" in data and not any(
        k in data for k in ("capabilities", "user_stories", "outcomes")
    ):
        typer.echo("File is already in unified entities format.", err=True)
        raise typer.Exit(0)

    # Mapping from section name to entity type
    section_to_type = {
        "capabilities": "capability",
        "user_stories": "user_story",
        "outcomes": "outcome",
    }

    # Get default type from config (if available)
    default_type: str | None = None
    config_path = get_config_path()
    if config_path and config_path.exists():
        with suppress(Exception):
            config = load_unified_config(config_path)
            if config.entity_types and config.entity_types.default_type:
                default_type = config.entity_types.default_type

    # Build unified entities section
    entities: dict[str, dict[str, Any]] = {}

    # Preserve existing entities if any
    if "entities" in data:
        entities.update(cast(dict[str, dict[str, Any]], data["entities"]))

    # Convert old sections
    for section_name, entity_type in section_to_type.items():
        if section_name in data and isinstance(data[section_name], dict):
            section_data = cast(dict[str, dict[str, Any]], data[section_name])
            for entity_id, entity_data in section_data.items():
                converted: dict[str, Any] = {}
                # Only add type field if it differs from default
                if entity_type != default_type:
                    converted["type"] = entity_type
                converted.update(entity_data)
                entities[entity_id] = converted

    # Build output data
    output_data: dict[str, Any] = {}

    # Preserve metadata if present
    if "metadata" in data:
        output_data["metadata"] = data["metadata"]

    # Add unified entities
    output_data["entities"] = entities

    # Output YAML (ruamel.yaml preserves block scalars and list formatting)
    yaml_rt.dump(output_data, sys.stdout)  # type: ignore[no-untyped-call]


# Register Jira subcommands (defined in jira_cli.py)
app.add_typer(jira_app, name="jira")

# Register report subcommands (defined in report_cli.py)
app.add_typer(report_app, name="report")


def _resolve_tag_filter(
    tags: list[str] | None,
    direction: str = "both",
) -> TagFilterSpec:
    """Parse CLI --tags and --tags-direction into a TagFilterSpec."""
    dir_val: Literal["both", "up", "down"] = "both"
    if direction == "up":
        dir_val = "up"
    elif direction == "down":
        dir_val = "down"
    elif direction != "both":
        typer.echo(
            f"Error: Invalid --tags-direction value '{direction}'. Must be one of: both, up, down",
            err=True,
        )
        raise typer.Exit(1)
    try:
        return parse_tag_options(tags, direction=dir_val)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from None


def _select_tag_entities(feature_map: FeatureMap, spec: TagFilterSpec) -> set[str] | None:
    """Select entities per spec and emit warning if empty. Return selected IDs or None."""
    if spec.is_empty:
        return None
    selected = select_entities(feature_map, spec)
    if selection_is_empty(selected, spec):
        typer.echo("warning: --tags matched no entities", err=True)
    return {e.id for e in selected}


@contextmanager
def _install_ephemeral_filter(
    selected_ids: set[str] | None,
) -> Generator[None, None, None]:
    """Context manager that installs an ephemeral entity filter for ``selected_ids``.

    No-op when ``selected_ids`` is None (empty spec). Unregisters on exit.
    """
    if selected_ids is None:
        yield
        return
    token = styling._register_filter_entity(  # pyright: ignore[reportPrivateUsage]
        priority=-1000,
        func=lambda entities, _ctx: [e for e in entities if e.id in selected_ids],
    )
    try:
        yield
    finally:
        styling._unregister_filter_entity(token)  # pyright: ignore[reportPrivateUsage]


@contextmanager
def _apply_tag_filter(
    feature_map: FeatureMap,
    spec: TagFilterSpec,
) -> Generator[None, None, None]:
    """Context manager that selects entities, emits empty-match warning, and installs ephemeral filter."""
    selected_ids = _select_tag_entities(feature_map, spec)
    with _install_ephemeral_filter(selected_ids):
        yield


def _load_styling(style_module: str | None, style_file: Path | None) -> None:
    """Load user styling module or file."""
    # Clear any previous registrations
    styling.clear_registrations()

    if style_module:
        # Import from module path
        importlib.import_module(style_module)
    elif style_file:
        # Import from file path
        style_path = style_file.resolve()
        spec = importlib.util.spec_from_file_location("user_styles", style_path)
        if spec is None or spec.loader is None:
            raise MoucError(f"Could not load styling file: {style_file}")
        user_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(user_module)


def _collect_style_tags(cli_style_tags: str | None, feature_map_path: Path) -> set[str]:
    """Collect style tags from CLI and config file.

    Args:
        cli_style_tags: Comma-separated tags from CLI --style-tags option
        feature_map_path: Path to feature map (used to find config file)

    Returns:
        Set of active style tags (CLI tags merged with config tags)
    """
    tags: set[str] = set()

    # Parse CLI tags
    if cli_style_tags:
        tags.update(tag.strip() for tag in cli_style_tags.split(",") if tag.strip())

    # Load config tags
    config_path = resolve_config_path(Path(feature_map_path))
    if config_path:
        with suppress(FileNotFoundError, ValueError):
            unified_config = load_unified_config(config_path)
            tags.update(unified_config.style_tags)

    return tags


def main() -> int:
    """Main entry point."""
    # Typer handles sys.exit() internally
    app()
    return 0


if __name__ == "__main__":
    main()
