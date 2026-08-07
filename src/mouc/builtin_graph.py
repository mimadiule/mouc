"""Built-in graph clustering function activated by the --cluster-by option.

Registered at priority=5 with formats=['graph'] so user @group_tasks functions
(priority=10) can override it and gantt output is never affected.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from . import styling
from .models import Entity as EntityModel

if TYPE_CHECKING:
    from .styling import Entity, GroupTasksFunc, StylingContext

_SCALAR_TYPES = (str, int, float, bool)


def validate_cluster_path(path: str) -> list[str]:
    """Split a dotted entity field path and validate its shape.

    Args:
        path: Dotted field path such as 'meta.repo'

    Returns:
        The path split into segments.

    Raises:
        ValueError: If a segment is empty or the first segment is not an Entity field.
    """
    segments = path.split(".")
    if any(not segment for segment in segments):
        raise ValueError(f"Invalid field path '{path}': empty path segment")

    entity_fields = {f.name for f in dataclasses.fields(EntityModel)}
    if segments[0] not in entity_fields:
        raise ValueError(f"Invalid field path '{path}': '{segments[0]}' is not an entity field")

    return segments


def resolve_cluster_value(entity: Entity, segments: list[str]) -> str | None:
    """Resolve a validated field path to a cluster key.

    Args:
        entity: Entity to read the field path from
        segments: Path segments from validate_cluster_path

    Returns:
        The cluster key, or None if the entity has no value for the path
        (missing, None, empty list, or the path does not apply to this entity).

    Raises:
        ValueError: If the path resolves to a value that cannot be a cluster key.
    """
    value: Any = getattr(entity, segments[0], None)
    for segment in segments[1:]:
        if not isinstance(value, dict):
            return None
        mapping = cast("dict[str, Any]", value)
        value = mapping.get(segment)

    if isinstance(value, list):
        items = cast("list[Any]", value)
        value = items[0] if items else None
    if value is None:
        return None
    if isinstance(value, _SCALAR_TYPES):
        return str(value)

    raise ValueError(
        f"Entity '{entity.id}': field path '{'.'.join(segments)}' resolves to a "
        f"{type(value).__name__}, which cannot be used as a cluster key"
    )


class BuiltinClustering(NamedTuple):
    """The registered --cluster-by grouping function and the path segments it resolves."""

    func: GroupTasksFunc
    segments: list[str]


def register_builtin_clustering(cluster_by: str | None) -> BuiltinClustering | None:
    """Register the --cluster-by built-in grouping function, replacing any prior one.

    Args:
        cluster_by: Dotted entity field path, or None to only clear prior registrations

    Returns:
        The registered function and its path segments, or None if nothing was registered.

    Raises:
        ValueError: If cluster_by is not a valid field path.
    """
    styling._replace_builtin_registrations(styling._group_tasks_funcs, "graph")
    if cluster_by is None:
        return None

    segments = validate_cluster_path(cluster_by)

    def _builtin_cluster_by_field(
        entities: Sequence[Entity], _context: StylingContext
    ) -> dict[str | None, list[Entity]]:
        """Group entities by the resolved value of the configured field path."""
        groups: dict[str, list[Entity]] = {}
        unclustered: list[Entity] = []

        for entity in entities:
            key = resolve_cluster_value(entity, segments)
            if key is None:
                unclustered.append(entity)
            else:
                groups.setdefault(key, []).append(entity)

        result: dict[str | None, list[Entity]] = {key: groups[key] for key in sorted(groups)}
        if unclustered:
            result[None] = unclustered
        return result

    styling._replace_builtin_registrations(
        styling._group_tasks_funcs, "graph", _builtin_cluster_by_field
    )
    return BuiltinClustering(_builtin_cluster_by_field, segments)
