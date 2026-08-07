"""Built-in gantt organization functions activated by config.

These functions are conditionally registered at initialization time based on
gantt configuration settings. They use priority=5 so user functions (priority=10)
can override them.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING

# Import registries directly (not through public API since this is internal)
from . import styling
from .scheduler import SchedulingConfig, parse_timeframe
from .styling import BUILTIN_PRIORITY
from .unified_config import DEFAULT_ENTITY_TYPES

if TYPE_CHECKING:
    from .styling import Entity, GroupTasksFunc, SortTasksFunc, StylingContext

__all__ = ["BUILTIN_PRIORITY", "register_builtin_organization"]


# ============================================================================
# Built-in Grouping Functions (Not Decorated - Registered Conditionally)
# ============================================================================


def _builtin_group_by_type(
    entities: Sequence[Entity], context: StylingContext
) -> dict[str | None, list[Entity]]:
    """Group entities by type."""
    # Get entity type order from config (or use default)
    config = getattr(context, "_config", {})
    gantt_config = config.get("gantt", {})
    type_order = gantt_config.get("entity_type_order", [])
    # Fall back to default entity types if not specified or empty
    if not type_order:
        type_order = [name for name, _ in DEFAULT_ENTITY_TYPES]

    # Initialize groups in order
    groups: dict[str, list[Entity]] = {t: [] for t in type_order}

    # Assign entities to groups
    for entity in entities:
        if entity.type in groups:
            groups[entity.type].append(entity)

    # Remove empty groups and format names
    result: dict[str | None, list[Entity]] = {}
    for entity_type, entity_list in groups.items():
        if entity_list:
            # Format type name for display: "user_story" -> "User Story"
            section_name = entity_type.replace("_", " ").title()
            result[section_name] = entity_list

    return result


def _builtin_group_by_resource(
    entities: Sequence[Entity], context: StylingContext
) -> dict[str | None, list[Entity]]:
    """Group entities by assigned resource."""
    groups: dict[str, list[Entity]] = {}

    # Assign entities to resource groups
    for entity in entities:
        # Get resources from schedule annotations
        sched = entity.annotations.get("schedule")
        resources: list[tuple[str, float]] = sched.resource_assignments if sched else []

        if not resources:
            # No resources assigned
            if "unassigned" not in groups:
                groups["unassigned"] = []
            groups["unassigned"].append(entity)
        else:
            # Add entity to each resource it's assigned to
            # resources is list[tuple[str, float]], extract resource name
            for resource_name, _ in resources:
                if resource_name not in groups:
                    groups[resource_name] = []
                groups[resource_name].append(entity)

    # Sort: alphabetically, with "unassigned" last
    sorted_keys = sorted(k for k in groups if k != "unassigned")
    if "unassigned" in groups:
        sorted_keys.append("unassigned")

    return {k: groups[k] for k in sorted_keys}


def _builtin_group_by_timeframe(
    entities: Sequence[Entity], context: StylingContext
) -> dict[str | None, list[Entity]]:
    """Group entities by timeframe metadata."""
    groups: dict[str, list[Entity]] = {}

    # Assign entities to timeframe groups
    for entity in entities:
        timeframe = entity.meta.get("timeframe", "Unscheduled")
        if timeframe not in groups:
            groups[timeframe] = []
        groups[timeframe].append(entity)

    # Sort timeframes lexically (works reasonably for Q1, Q2, 2025-Q1 formats)
    return dict(sorted(groups.items()))


# ============================================================================
# Built-in Sorting Functions (Not Decorated - Registered Conditionally)
# ============================================================================


def _builtin_sort_by_start(entities: Sequence[Entity], _context: StylingContext) -> list[Entity]:
    """Sort entities by start date ascending."""

    def get_start(entity: Entity) -> date:
        sched = entity.annotations.get("schedule")
        return sched.estimated_start if sched and sched.estimated_start else date.max

    return sorted(entities, key=get_start)


def _builtin_sort_by_end(entities: Sequence[Entity], _context: StylingContext) -> list[Entity]:
    """Sort entities by end date ascending."""

    def get_end(entity: Entity) -> date:
        sched = entity.annotations.get("schedule")
        return sched.estimated_end if sched and sched.estimated_end else date.max

    return sorted(entities, key=get_end)


def _builtin_sort_by_deadline(entities: Sequence[Entity], _context: StylingContext) -> list[Entity]:
    """Sort entities by deadline (end_before or timeframe end) ascending."""

    def get_deadline(entity: Entity) -> date:
        # Try end_before first
        end_before = entity.meta.get("end_before")
        if end_before:
            if isinstance(end_before, date):
                return end_before
            if isinstance(end_before, str):
                try:
                    return date.fromisoformat(end_before)
                except ValueError:
                    pass

        # Try timeframe end
        timeframe = entity.meta.get("timeframe")
        if timeframe and isinstance(timeframe, str):
            try:
                _, end_date = parse_timeframe(timeframe)
                if end_date:
                    return end_date
            except (ValueError, TypeError):
                pass

        # No deadline found
        return date.max

    return sorted(entities, key=get_deadline)


def _builtin_sort_by_name(entities: Sequence[Entity], _context: StylingContext) -> list[Entity]:
    """Sort entities alphabetically by name."""
    return sorted(entities, key=lambda e: e.name.lower())


def _builtin_sort_by_priority(entities: Sequence[Entity], context: StylingContext) -> list[Entity]:
    """Sort entities by priority metadata descending (higher priority first)."""
    # Get default priority from scheduler config (fall back to config class default)
    default_priority = SchedulingConfig().default_priority
    config: dict[str, object] | None = getattr(context, "_config", None)
    if config is not None:
        scheduler_config = config.get("scheduler")
        if isinstance(scheduler_config, dict):
            sched_dict: dict[str, object] = scheduler_config  # type: ignore[assignment]
            config_priority = sched_dict.get("default_priority")
            if isinstance(config_priority, int):
                default_priority = config_priority

    def get_priority(entity: Entity) -> int:
        return -entity.meta.get("priority", default_priority)  # Negative for descending sort

    return sorted(entities, key=get_priority)


# ============================================================================
# Registration Helper
# ============================================================================

# 'none'/'yaml_order'/None and unrecognized values are absent, registering nothing
_GROUP_BY_FUNCS: dict[str, GroupTasksFunc] = {
    "type": _builtin_group_by_type,
    "resource": _builtin_group_by_resource,
    "timeframe": _builtin_group_by_timeframe,
}

_SORT_BY_FUNCS: dict[str, SortTasksFunc] = {
    "start": _builtin_sort_by_start,
    "end": _builtin_sort_by_end,
    "deadline": _builtin_sort_by_deadline,
    "name": _builtin_sort_by_name,
    "priority": _builtin_sort_by_priority,
}


def register_builtin_organization(group_by: str | None, sort_by: str | None) -> None:
    """Conditionally register built-in organization functions based on config.

    This function is called during GanttScheduler initialization to register
    the appropriate built-in functions based on the gantt configuration.

    Built-in functions are registered at priority=5, so user functions (priority=10)
    can override them.

    Args:
        group_by: Grouping strategy ('type', 'resource', 'timeframe', 'none', or None)
        sort_by: Sorting strategy ('start', 'end', 'deadline', 'name', 'priority', 'yaml_order', or None)
    """
    styling._replace_builtin_registrations(
        styling._group_tasks_funcs, "gantt", _GROUP_BY_FUNCS.get(group_by or "")
    )
    styling._replace_builtin_registrations(
        styling._sort_tasks_funcs, "gantt", _SORT_BY_FUNCS.get(sort_by or "")
    )
