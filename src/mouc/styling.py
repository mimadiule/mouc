"""Styling system for Mouc graphs and markdown output."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypedDict, TypeVar, overload

if TYPE_CHECKING:
    from .models import FeatureMap

# Constants for color calculations
HEX_COLOR_SHORT_LENGTH = 3  # Length of shorthand hex colors (#RGB)
HEX_COLOR_FULL_LENGTH = 6  # Length of full hex colors (#RRGGBB)
WCAG_LUMINANCE_THRESHOLD = 0.03928  # WCAG luminance calculation threshold
WCAG_CONTRAST_MIDPOINT = 0.5  # Luminance midpoint for contrast determination
HSL_LIGHTNESS_MIDPOINT = 0.5  # HSL lightness midpoint for color conversion


# ============================================================================
# Public Protocols
# ============================================================================


class Entity(Protocol):
    """Entity interface for styling functions."""

    @property
    def type(self) -> str:
        """Entity type: 'capability', 'user_story', or 'outcome'."""
        ...

    @property
    def id(self) -> str:
        """Unique entity identifier."""
        ...

    @property
    def name(self) -> str:
        """Human-readable entity name."""
        ...

    @property
    def description(self) -> str:
        """Entity description."""
        ...

    @property
    def requires_ids(self) -> set[str]:
        """Set of entity IDs this entity directly depends on."""
        ...

    @property
    def enables_ids(self) -> set[str]:
        """Set of entity IDs that directly depend on this entity."""
        ...

    @property
    def tags(self) -> list[str]:
        """List of tags for this entity."""
        ...

    @property
    def meta(self) -> dict[str, Any]:
        """Free-form metadata dictionary."""
        ...

    @property
    def annotations(self) -> dict[str, Any]:
        """Computed annotations dictionary (e.g., schedule annotations)."""
        ...

    @property
    def parsed_links(self) -> Sequence[Link]:
        """Parsed link objects."""
        ...


class Link(Protocol):
    """Link interface for styling functions."""

    @property
    def type(self) -> str | None:
        """Link type (e.g., 'jira', 'design', 'doc')."""
        ...

    @property
    def label(self) -> str:
        """Link label text."""
        ...

    @property
    def url(self) -> str | None:
        """Link URL if available."""
        ...


class StylingContext(Protocol):
    """Context providing graph analysis and queries for styling functions."""

    def get_entity(self, entity_id: str) -> Entity | None:
        """Get entity by ID, or None if not found."""
        ...

    def get_all_entities(self) -> list[Entity]:
        """Get all entities in the graph."""
        ...

    def get_entities_by_type(self, entity_type: str) -> list[Entity]:
        """Get all entities of a given type."""
        ...

    def transitively_requires(self, entity_id: str) -> set[str]:
        """Get all entity IDs that this entity transitively depends on.

        Follows 'requires' edges backward through the dependency graph.
        Returns empty set if entity not found.
        """
        ...

    def transitively_enables(self, entity_id: str) -> set[str]:
        """Get all entity IDs that this entity transitively enables.

        Follows 'enables' edges forward through the dependency graph.
        If this entity is a capability, returns all user stories and outcomes
        that cannot be completed without this capability.
        Returns empty set if entity not found.
        """
        ...

    def get_leaf_entities(self) -> set[str]:
        """Get entity IDs that don't enable anything (graph leaves)."""
        ...

    def get_root_entities(self) -> set[str]:
        """Get entity IDs that don't require anything (graph roots)."""
        ...

    def collect_metadata_values(self, key: str) -> list[str]:
        """Collect all unique values for a metadata key across all entities.

        Results are sorted and cached for performance.
        Example: context.collect_metadata_values('timeframe') -> ['Q1', 'Q2', 'Q3']
        """
        ...

    @property
    def output_format(self) -> str | None:
        """Output format being generated ('markdown', 'docx', 'gantt', etc.).

        Returns None if format is not specified or not applicable.
        """
        ...

    @property
    def style_tags(self) -> set[str]:
        """Active style tags for filtering styling functions.

        Returns empty set if no tags are active.
        """
        ...


# ============================================================================
# Return Type Definitions
# ============================================================================


class NodeStyle(TypedDict, total=False):
    """Graphviz node attributes.

    Common attributes (see Graphviz documentation for complete list):
        shape: 'oval', 'box', 'diamond', 'hexagon', etc.
        fill_color: CSS color or hex string
        text_color: CSS color or hex string
        border_color: CSS color or hex string
        border_width: int
        fontsize: int
        fontname: str
    """

    shape: str
    fill_color: str
    text_color: str
    border_color: str
    border_width: int
    fontsize: int
    fontname: str


class EdgeStyle(TypedDict, total=False):
    """Graphviz edge attributes.

    Common attributes:
        color: CSS color or hex string
        style: 'solid', 'dashed', 'dotted'
        penwidth: int
        arrowhead: 'normal', 'none', 'vee', etc.
    """

    color: str
    style: Literal["solid", "dashed", "dotted"]
    penwidth: int
    arrowhead: str


class TaskStyle(TypedDict, total=False):
    """Mermaid gantt task styling attributes.

    Mermaid gantt charts support both task tags and custom CSS styling via themeCSS.

    Task tags (predefined visual styles):
        - 'done': Completed tasks (green)
        - 'crit': Critical tasks (red)
        - 'active': In-progress tasks (blue)
        - 'milestone': Milestone markers

    CSS properties (custom colors via themeCSS in YAML frontmatter):
        - fill_color: Task bar fill color (e.g., '#ff0000', 'CadetBlue')
        - stroke_color: Task bar border color
        - text_color: Task text color

    Attributes:
        tags: List of Mermaid task tags
        section: Optional section name to group tasks under
        fill_color: CSS color for task bar fill
        stroke_color: CSS color for task bar border
        text_color: CSS color for task text
    """

    tags: list[str]
    section: str
    fill_color: str
    stroke_color: str
    text_color: str


# ============================================================================
# Type Aliases for Function Signatures
# ============================================================================

NodeStylerFunc = Callable[[Entity, StylingContext], NodeStyle]
EdgeStylerFunc = Callable[[str, str, str, StylingContext], EdgeStyle]
LabelStylerFunc = Callable[[Entity, StylingContext], str | None]
TaskStylerFunc = Callable[[Entity, StylingContext], TaskStyle]
MetadataStylerFunc = Callable[[Entity, StylingContext, dict[str, Any]], dict[str, Any]]

# Task organization function signatures
GroupTasksFunc = Callable[[Sequence[Entity], StylingContext], dict[str | None, list[Entity]]]
SortTasksFunc = Callable[[Sequence[Entity], StylingContext], list[Entity]]

# Entity filtering function signature
FilterEntityFunc = Callable[[Sequence[Entity], StylingContext], list[Entity]]


# ============================================================================
# Internal Registry
# ============================================================================

_F = TypeVar("_F", bound=Callable[..., Any])


@dataclass(frozen=True, slots=True)
class StylerRegistration(Generic[_F]):
    """Registration entry for a styling function."""

    priority: int
    formats: list[str] | None
    tags: list[str] | None
    func: _F


_node_stylers: list[StylerRegistration[NodeStylerFunc]] = []
_edge_stylers: list[StylerRegistration[EdgeStylerFunc]] = []
_label_stylers: list[StylerRegistration[LabelStylerFunc]] = []
_task_stylers: list[StylerRegistration[TaskStylerFunc]] = []
_metadata_stylers: list[StylerRegistration[MetadataStylerFunc]] = []

# Task organization registries
_group_tasks_funcs: list[StylerRegistration[GroupTasksFunc]] = []
_sort_tasks_funcs: list[StylerRegistration[SortTasksFunc]] = []

# Entity filtering registry
_filter_entity_funcs: list[StylerRegistration[FilterEntityFunc]] = []


# ============================================================================
# Public Decorators
# ============================================================================


@overload
def style_node(func: NodeStylerFunc) -> NodeStylerFunc: ...


@overload
def style_node(
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> Callable[[NodeStylerFunc], NodeStylerFunc]: ...


def style_node(
    func: NodeStylerFunc | None = None,
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> NodeStylerFunc | Callable[[NodeStylerFunc], NodeStylerFunc]:
    """Register a node styling function.

    The function receives an entity and context, and returns a dict of
    graphviz node attributes to apply.

    Multiple functions are applied in priority order (lower numbers first).
    Later functions override earlier ones for conflicting attributes.

    Signature: (entity: Entity, context: StylingContext) -> NodeStyle

    Args:
        priority: Execution priority (lower numbers first)
        formats: Optional list of formats to apply to (e.g., ['graph']). None means all formats.
        tags: Optional list of tags that enable this function. None means always run.
              Positive tags use OR logic (any match enables). Negated tags (prefixed
              with '!') use AND logic (all must be absent).

    Examples:
        @style_node
        def my_styler(entity, context):
            return {'fill_color': '#ff0000'}

        @style_node(priority=20, formats=['graph'])
        def graph_only_styler(entity, context):
            return {'border_color': '#00ff00'}

        @style_node(tags=['detailed'])
        def detailed_styler(entity, context):
            return {'fontsize': 14}

        @style_node(tags=['!detailed'])
        def compact_styler(entity, context):
            # Runs only when 'detailed' tag is NOT active
            return {'fontsize': 10}
    """

    def decorator(f: NodeStylerFunc) -> NodeStylerFunc:
        _node_stylers.append(StylerRegistration(priority, formats, tags, f))
        return f

    if func is None:
        # Called with arguments: @style_node(priority=20)
        return decorator
    # Called without arguments: @style_node
    return decorator(func)


@overload
def style_edge(func: EdgeStylerFunc) -> EdgeStylerFunc: ...


@overload
def style_edge(
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> Callable[[EdgeStylerFunc], EdgeStylerFunc]: ...


def style_edge(
    func: EdgeStylerFunc | None = None,
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> EdgeStylerFunc | Callable[[EdgeStylerFunc], EdgeStylerFunc]:
    """Register an edge styling function.

    The function receives edge endpoints, edge type, and context, and returns
    a dict of graphviz edge attributes to apply.

    Signature: (from_id: str, to_id: str, edge_type: str, context: StylingContext) -> EdgeStyle

    Args:
        priority: Execution priority (lower numbers first)
        formats: Optional list of formats to apply to (e.g., ['graph']). None means all formats.
        tags: Optional list of tags that enable this function. None means always run.
              Positive tags use OR logic (any match enables). Negated tags (prefixed
              with '!') use AND logic (all must be absent).

    Edge types:
        - 'requires': entity depends on another
        - 'enables': entity enables another (reverse of requires)

    Example:
        @style_edge
        def my_edge_styler(from_id, to_id, edge_type, context):
            return {'color': '#666666', 'style': 'solid'}
    """

    def decorator(f: EdgeStylerFunc) -> EdgeStylerFunc:
        _edge_stylers.append(StylerRegistration(priority, formats, tags, f))
        return f

    if func is None:
        # Called with arguments: @style_edge(priority=20)
        return decorator
    # Called without arguments: @style_edge
    return decorator(func)


@overload
def style_label(func: LabelStylerFunc) -> LabelStylerFunc: ...


@overload
def style_label(
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> Callable[[LabelStylerFunc], LabelStylerFunc]: ...


def style_label(
    func: LabelStylerFunc | None = None,
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> LabelStylerFunc | Callable[[LabelStylerFunc], LabelStylerFunc]:
    """Register a markdown label styling function.

    The function receives an entity and context, and returns a string that
    replaces the default type label (e.g., '[Capability]') in markdown output.

    Return empty string to hide the label entirely or None to use default (or apply next styler)

    Multiple functions are applied in priority order. The last non-None
    result is used.

    Signature: (entity: Entity, context: StylingContext) -> str | None

    Args:
        priority: Execution priority (lower numbers first)
        formats: Optional list of formats to apply to (e.g., ['markdown', 'docx']). None means all formats.
        tags: Optional list of tags that enable this function. None means always run.
              Positive tags use OR logic (any match enables). Negated tags (prefixed
              with '!') use AND logic (all must be absent).

    Example:
        @style_label
        def show_milestones(entity, context):
            enabled = context.transitively_enables(entity.id)
            milestones = [e for e in enabled if 'milestone' in context.get_entity(e).tags]
            if milestones:
                return ' '.join(f'[{m}]' for m in milestones)
            return ''
    """

    def decorator(f: LabelStylerFunc) -> LabelStylerFunc:
        _label_stylers.append(StylerRegistration(priority, formats, tags, f))
        return f

    if func is None:
        # Called with arguments: @style_label(priority=20)
        return decorator
    # Called without arguments: @style_label
    return decorator(func)


@overload
def style_task(func: TaskStylerFunc) -> TaskStylerFunc: ...


@overload
def style_task(
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> Callable[[TaskStylerFunc], TaskStylerFunc]: ...


def style_task(
    func: TaskStylerFunc | None = None,
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> TaskStylerFunc | Callable[[TaskStylerFunc], TaskStylerFunc]:
    """Register a gantt task styling function.

    The function receives an entity and context, and returns a dict of
    Mermaid gantt task attributes to apply.

    Multiple functions are applied in priority order (lower numbers first).
    Later functions override earlier ones for conflicting attributes.

    Signature: (entity: Entity, context: StylingContext) -> TaskStyle

    Args:
        priority: Execution priority (lower numbers first)
        formats: Optional list of formats to apply to (e.g., ['gantt']). None means all formats.
        tags: Optional list of tags that enable this function. None means always run.
              Positive tags use OR logic (any match enables). Negated tags (prefixed
              with '!') use AND logic (all must be absent).

    Mermaid supports the following task tags:
        - 'done': Marks completed tasks (green)
        - 'crit': Marks critical path tasks (red)
        - 'active': Marks tasks in progress (blue)
        - 'milestone': Single-point-in-time events

    CSS properties (applied via themeCSS in YAML frontmatter):
        - 'fill_color': Task bar fill color (CSS color value)
        - 'stroke_color': Task bar border color (CSS color value)
        - 'text_color': Task text color (CSS color value)

    Examples:
        @style_task
        def style_by_status(entity, context):
            if entity.meta.get('status') == 'complete':
                return {'tags': ['done']}
            return {'tags': ['active']}

        @style_task(priority=20)
        def color_by_team(entity, context):
            team = entity.meta.get('team')
            colors = {'platform': '#4287f5', 'backend': '#42f554'}
            if team in colors:
                return {'fill_color': colors[team]}
            return {}
    """

    def decorator(f: TaskStylerFunc) -> TaskStylerFunc:
        _task_stylers.append(StylerRegistration(priority, formats, tags, f))
        return f

    if func is None:
        # Called with arguments: @style_task(priority=20)
        return decorator
    # Called without arguments: @style_task
    return decorator(func)


@overload
def style_metadata(func: MetadataStylerFunc) -> MetadataStylerFunc: ...


@overload
def style_metadata(
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> Callable[[MetadataStylerFunc], MetadataStylerFunc]: ...


def style_metadata(
    func: MetadataStylerFunc | None = None,
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> MetadataStylerFunc | Callable[[MetadataStylerFunc], MetadataStylerFunc]:
    """Register a metadata styling function for markdown output.

    The function receives an entity, context, and current metadata dict,
    and returns a new metadata dict to display. Functions are chained in
    priority order - the output of one becomes the input to the next.

    This allows styling functions to add computed fields (like schedule
    annotations) to the markdown metadata table without mutating entity.meta.

    Signature: (entity: Entity, context: StylingContext, metadata: dict) -> dict

    Args:
        priority: Execution priority (lower numbers first)
        formats: Optional list of formats to apply to (e.g., ['markdown', 'docx']). None means all formats.
        tags: Optional list of tags that enable this function. None means always run.
              Positive tags use OR logic (any match enables). Negated tags (prefixed
              with '!') use AND logic (all must be absent).

    Examples:
        @style_metadata
        def add_schedule_info(entity, context, metadata):
            schedule = entity.annotations.get('schedule')
            if not schedule:
                return metadata

            result = metadata.copy()
            if schedule.estimated_start:
                result['Estimated Start'] = str(schedule.estimated_start)
            return result

        @style_metadata(priority=20, formats=['docx'])
        def filter_for_docx(entity, context, metadata):
            # Only applies to docx output
            result = metadata.copy()
            result.pop('verbose_field', None)
            return result
    """

    def decorator(f: MetadataStylerFunc) -> MetadataStylerFunc:
        _metadata_stylers.append(StylerRegistration(priority, formats, tags, f))
        return f

    if func is None:
        # Called with arguments: @style_metadata(priority=20)
        return decorator
    # Called without arguments: @style_metadata
    return decorator(func)


@overload
def group_tasks(func: GroupTasksFunc) -> GroupTasksFunc: ...


@overload
def group_tasks(
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> Callable[[GroupTasksFunc], GroupTasksFunc]: ...


def group_tasks(
    func: GroupTasksFunc | None = None,
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> GroupTasksFunc | Callable[[GroupTasksFunc], GroupTasksFunc]:
    """Register a task grouping function for gantt charts.

    The function receives a list of entities and context, and returns
    a dict mapping section names to entity lists. Dict insertion order determines
    display order.

    Only ONE grouping function is active (highest priority wins).

    Signature: (entities: Sequence[Entity], context: StylingContext) -> dict[str | None, list[Entity]]

    Args:
        priority: Execution priority (higher number = higher priority, user functions default to 10,
                 built-in config functions use 5)
        formats: Optional list of formats to apply to (e.g., ['gantt']). None means all formats.
        tags: Optional list of tags that enable this function. None means always run.
              Positive tags use OR logic (any match enables). Negated tags (prefixed
              with '!') use AND logic (all must be absent).

    Return dict mapping:
        - Keys: Section names (str) or None for no section
        - Values: Lists of entities to include in that section
        - Dict order determines section display order

    Examples:
        @group_tasks(formats=['gantt'])
        def group_by_milestone(entities, context):
            groups = {}
            for entity in entities:
                milestone = entity.meta.get('milestone', 'Other')
                if milestone not in groups:
                    groups[milestone] = []
                groups[milestone].append(entity)
            return groups  # dict order = display order

        @group_tasks(priority=20)
        def group_by_team(entities, context):
            groups = {}
            for entity in entities:
                team = entity.meta.get('team', 'unassigned')
                if team not in groups:
                    groups[team] = []
                groups[team].append(entity)
            # Sort groups alphabetically
            return dict(sorted(groups.items()))
    """

    def decorator(f: GroupTasksFunc) -> GroupTasksFunc:
        _group_tasks_funcs.append(StylerRegistration(priority, formats, tags, f))
        return f

    if func is None:
        # Called with arguments: @group_tasks(priority=20)
        return decorator
    # Called without arguments: @group_tasks
    return decorator(func)


@overload
def sort_tasks(func: SortTasksFunc) -> SortTasksFunc: ...


@overload
def sort_tasks(
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> Callable[[SortTasksFunc], SortTasksFunc]: ...


def sort_tasks(
    func: SortTasksFunc | None = None,
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> SortTasksFunc | Callable[[SortTasksFunc], SortTasksFunc]:
    """Register a task sorting function for gantt charts.

    The function receives a flat list of entities (from one group) and returns
    a sorted list. This is called once per group after grouping is applied.

    Only ONE sorting function is active (highest priority wins).

    Signature: (entities: Sequence[Entity], context: StylingContext) -> list[Entity]

    Args:
        priority: Execution priority (higher number = higher priority, user functions default to 10,
                 built-in config functions use 5)
        formats: Optional list of formats to apply to (e.g., ['gantt']). None means all formats.
        tags: Optional list of tags that enable this function. None means always run.
              Positive tags use OR logic (any match enables). Negated tags (prefixed
              with '!') use AND logic (all must be absent).

    Examples:
        @sort_tasks(formats=['gantt'])
        def sort_by_start_date(entities, context):
            def get_start(e):
                sched = e.annotations.get('schedule')
                return sched.estimated_start if sched else date.max
            return sorted(entities, key=get_start)

        @sort_tasks(priority=20)
        def sort_critical_first(entities, context):
            def sort_key(entity):
                is_critical = 'critical' in entity.tags
                sched = entity.annotations.get('schedule')
                start = sched.estimated_start if sched else date.max
                return (not is_critical, start)  # False < True
            return sorted(entities, key=sort_key)
    """

    def decorator(f: SortTasksFunc) -> SortTasksFunc:
        _sort_tasks_funcs.append(StylerRegistration(priority, formats, tags, f))
        return f

    if func is None:
        # Called with arguments: @sort_tasks(priority=20)
        return decorator
    # Called without arguments: @sort_tasks
    return decorator(func)


@overload
def filter_entity(func: FilterEntityFunc) -> FilterEntityFunc: ...


@overload
def filter_entity(
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> Callable[[FilterEntityFunc], FilterEntityFunc]: ...


def filter_entity(
    func: FilterEntityFunc | None = None,
    *,
    priority: int = 10,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> FilterEntityFunc | Callable[[FilterEntityFunc], FilterEntityFunc]:
    """Register an entity filtering function that works across all output types.

    The function receives a sequence of entities and context, and returns a filtered
    list of entities. Multiple filters are chained in priority order (lower first).

    Signature: (entities: Sequence[Entity], context: StylingContext) -> list[Entity]

    Args:
        priority: Execution priority (lower numbers first). Default is 10.
        formats: Optional list of formats to apply to (e.g., ['gantt', 'markdown']).
                None means all formats (markdown, docx, graph, gantt).
        tags: Optional list of tags that enable this function. None means always run.
              Positive tags use OR logic (any match enables). Negated tags (prefixed
              with '!') use AND logic (all must be absent).

    Examples:
        @filter_entity(formats=['gantt'])
        def filter_completed(entities, context):
            '''Exclude completed tasks from gantt charts.'''
            return [e for e in entities if e.meta.get('status') != 'done']

        @filter_entity(priority=5)
        def filter_by_tags(entities, context):
            '''Include only entities with specific tags.'''
            allowed_tags = {'backend', 'frontend'}
            return [e for e in entities if any(tag in allowed_tags for tag in e.tags)]

        @filter_entity(formats=['markdown', 'docx'], tags=['quarterly-report'])
        def filter_by_timeframe(entities, context):
            '''Include only Q1 entities in documents (when quarterly-report tag is active).'''
            return [e for e in entities if e.meta.get('timeframe', '').startswith('2025-Q1')]
    """

    def decorator(f: FilterEntityFunc) -> FilterEntityFunc:
        _register_filter_entity(priority=priority, func=f, formats=formats, tags=tags)
        return f

    if func is None:
        # Called with arguments: @filter_entity(priority=20)
        return decorator
    # Called without arguments: @filter_entity
    return decorator(func)


def _register_filter_entity(
    *,
    priority: int,
    func: FilterEntityFunc,
    formats: list[str] | None = None,
    tags: list[str] | None = None,
) -> StylerRegistration[FilterEntityFunc]:
    """Register an entity filter function and return its registration token.

    The token can be passed to ``_unregister_filter_entity`` to remove the filter.
    """
    reg: StylerRegistration[FilterEntityFunc] = StylerRegistration(priority, formats, tags, func)
    _filter_entity_funcs.append(reg)
    return reg


def _unregister_filter_entity(token: StylerRegistration[FilterEntityFunc]) -> None:
    """Remove a previously registered entity filter by its token (identity match).

    Silent no-op if token is absent (e.g., registry was cleared between register and unregister).
    """
    for i, reg in enumerate(_filter_entity_funcs):
        if reg is token:
            del _filter_entity_funcs[i]
            return


# ============================================================================
# Utility Functions
# ============================================================================


def sequential_hue(
    value: str,
    all_values: list[str],
    hue_range: tuple[int, int] = (120, 230),
    lightness_range: tuple[int, int] = (95, 75),
    saturation: int = 60,
) -> str:
    """Generate RGB hex color for sequential categorical values.

    Maps values to colors evenly distributed across the hue range.

    Args:
        value: The value to color
        all_values: All possible values (determines position in sequence)
        hue_range: HSL hue range in degrees (0-360)
        lightness_range: HSL lightness range (0-100), can be reversed for dark->light
        saturation: HSL saturation (0-100)

    Returns:
        RGB hex color string like '#80e5cc'

    Example:
        timeframes = ['Q1', 'Q2', 'Q3', 'Q4']
        color = sequential_hue('Q2', timeframes)  # Returns '#...'
    """
    if not all_values:
        return _hsl_to_hex(hue_range[0], saturation, lightness_range[0])

    try:
        index = all_values.index(value)
    except ValueError:
        # Value not in list, use default
        return _hsl_to_hex(hue_range[0], saturation, lightness_range[0])

    # Calculate position in sequence
    progress = 0.5 if len(all_values) == 1 else index / (len(all_values) - 1)

    # Interpolate hue and lightness
    hue = hue_range[0] + (hue_range[1] - hue_range[0]) * progress
    lightness = lightness_range[0] + (lightness_range[1] - lightness_range[0]) * progress

    return _hsl_to_hex(hue, saturation, lightness)


def contrast_text_color(bg_color: str) -> str:
    """Compute readable text color (black or white) for a background color.

    Uses WCAG luminance calculations to ensure readability.

    Args:
        bg_color: Background color (hex like '#ff0000')

    Returns:
        '#000000' or '#ffffff'

    Example:
        bg = sequential_hue('Q2', timeframes)  # Returns hex color
        fg = contrast_text_color(bg)
        return {'fill_color': bg, 'text_color': fg}
    """
    # Parse hex color
    if not bg_color.startswith("#"):
        return "#000000"  # Invalid format, default to black

    hex_color = bg_color.lstrip("#")
    if len(hex_color) == HEX_COLOR_SHORT_LENGTH:
        # Expand shorthand hex (#RGB -> #RRGGBB)
        hex_color = "".join(c * 2 for c in hex_color)
    elif len(hex_color) != HEX_COLOR_FULL_LENGTH:
        return "#000000"  # Invalid hex length

    try:
        r = int(hex_color[0:2], 16) / 255
        g = int(hex_color[2:4], 16) / 255
        b = int(hex_color[4:6], 16) / 255
    except ValueError:
        return "#000000"  # Invalid hex characters

    # Calculate relative luminance using WCAG formula
    def luminance_component(c: float) -> float:
        return c / 12.92 if c <= WCAG_LUMINANCE_THRESHOLD else ((c + 0.055) / 1.055) ** 2.4

    luminance = (
        0.2126 * luminance_component(r)
        + 0.7152 * luminance_component(g)
        + 0.0722 * luminance_component(b)
    )

    # Use white text on dark backgrounds, black on light
    return "#ffffff" if luminance < WCAG_CONTRAST_MIDPOINT else "#000000"


# ============================================================================
# Internal Functions
# ============================================================================


def _hsl_to_hex(h: float, s: float, lightness: float) -> str:
    """Convert HSL color to RGB hex format.

    Args:
        h: Hue in degrees (0-360)
        s: Saturation as percentage (0-100)
        lightness: Lightness as percentage (0-100)

    Returns:
        Hex color string like "#RRGGBB"
    """
    h = h / 360
    s = s / 100
    lightness = lightness / 100

    if s == 0:
        r = g = b = lightness
    else:

        def hue_to_rgb(p: float, q: float, t: float) -> float:
            if t < 0:
                t += 1
            if t > 1:
                t -= 1
            if t < 1 / 6:
                return p + (q - p) * 6 * t
            if t < 1 / 2:
                return q
            if t < 2 / 3:
                return p + (q - p) * (2 / 3 - t) * 6
            return p

        q = (
            lightness * (1 + s)
            if lightness < HSL_LIGHTNESS_MIDPOINT
            else lightness + s - lightness * s
        )
        p = 2 * lightness - q
        r = hue_to_rgb(p, q, h + 1 / 3)
        g = hue_to_rgb(p, q, h)
        b = hue_to_rgb(p, q, h - 1 / 3)

    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def clear_registrations() -> None:
    """Clear all registered styling functions (called before loading user module)."""
    _node_stylers.clear()
    _edge_stylers.clear()
    _label_stylers.clear()
    _task_stylers.clear()
    _metadata_stylers.clear()
    _group_tasks_funcs.clear()
    _sort_tasks_funcs.clear()
    _filter_entity_funcs.clear()


def _tags_match(func_tags: list[str] | None, active_tags: set[str]) -> bool:
    """Check if a function's tags match the active style tags.

    Supports negated tags with '!' prefix (e.g., '!detailed' matches when
    'detailed' is NOT active). Multiple negated tags use AND logic (all must
    be absent). Positive tags use OR logic (at least one must match).

    Args:
        func_tags: Tags specified on the function (None = always run)
        active_tags: Currently active style tags

    Returns:
        True if the function should run, False otherwise
    """
    # None means no tag requirement - always run
    if func_tags is None:
        return True

    positive_tags: list[str] = []
    negated_tags: list[str] = []
    for tag in func_tags:
        if tag.startswith("!"):
            negated_tags.append(tag[1:])
        else:
            positive_tags.append(tag)

    # All negated tags must be absent (AND logic)
    for neg_tag in negated_tags:
        if neg_tag in active_tags:
            return False

    # If no positive tags, negations alone are sufficient
    if not positive_tags:
        return True

    # At least one positive tag must match (OR logic)
    return bool(set(positive_tags) & active_tags)


def apply_node_styles(entity: Entity, context: StylingContext) -> dict[str, Any]:
    """Apply all registered node styling functions in priority order."""
    # Sort by priority (lower numbers first)
    stylers = sorted(_node_stylers, key=lambda x: x.priority)
    active_tags = context.style_tags

    # Merge results - later overrides earlier
    final_style: dict[str, Any] = {}
    for reg in stylers:
        # Skip if format filter is set and doesn't match
        if reg.formats is not None and context.output_format not in reg.formats:
            continue
        # Skip if tags specified but none match active tags
        if not _tags_match(reg.tags, active_tags):
            continue

        result = reg.func(entity, context)
        if result:
            final_style.update(result)

    return final_style


def apply_edge_styles(
    from_id: str, to_id: str, edge_type: str, context: StylingContext
) -> dict[str, Any]:
    """Apply all registered edge styling functions in priority order."""
    # Sort by priority (lower numbers first)
    stylers = sorted(_edge_stylers, key=lambda x: x.priority)
    active_tags = context.style_tags

    # Merge results - later overrides earlier
    final_style: dict[str, Any] = {}
    for reg in stylers:
        # Skip if format filter is set and doesn't match
        if reg.formats is not None and context.output_format not in reg.formats:
            continue
        # Skip if tags specified but none match active tags
        if not _tags_match(reg.tags, active_tags):
            continue

        result = reg.func(from_id, to_id, edge_type, context)
        if result:
            final_style.update(result)

    return final_style


def apply_label_styles(entity: Entity, context: StylingContext) -> str | None:
    """Apply all registered label styling functions in priority order.

    Returns the last non-None result, or None if no stylers or all return None.
    """
    # Sort by priority (lower numbers first)
    stylers = sorted(_label_stylers, key=lambda x: x.priority)
    active_tags = context.style_tags

    # Apply in order, keeping track of last non-None result
    label = None
    for reg in stylers:
        # Skip if format filter is set and doesn't match
        if reg.formats is not None and context.output_format not in reg.formats:
            continue
        # Skip if tags specified but none match active tags
        if not _tags_match(reg.tags, active_tags):
            continue

        result = reg.func(entity, context)
        if result is not None:
            label = result

    return label


def apply_task_styles(entity: Entity, context: StylingContext) -> dict[str, Any]:
    """Apply all registered task styling functions in priority order."""
    # Sort by priority (lower numbers first)
    stylers = sorted(_task_stylers, key=lambda x: x.priority)
    active_tags = context.style_tags

    # Merge results - later overrides earlier
    final_style: dict[str, Any] = {}
    for reg in stylers:
        # Skip if format filter is set and doesn't match
        if reg.formats is not None and context.output_format not in reg.formats:
            continue
        # Skip if tags specified but none match active tags
        if not _tags_match(reg.tags, active_tags):
            continue

        result = reg.func(entity, context)
        if result:
            # Special handling for tags - merge lists instead of replacing
            if "tags" in result and "tags" in final_style:
                # Combine and deduplicate tags
                existing_tags = final_style["tags"]
                new_tags = result["tags"]
                final_style["tags"] = list(dict.fromkeys(existing_tags + new_tags))
            else:
                final_style.update(result)

    return final_style


def apply_metadata_styles(
    entity: Entity, context: StylingContext, base_metadata: dict[str, Any]
) -> dict[str, Any]:
    """Apply all registered metadata styling functions in priority order.

    Functions are chained - the output of one becomes the input to the next.
    This allows pure functional composition without mutation.

    Args:
        entity: The entity being styled
        context: The styling context
        base_metadata: The initial metadata dict (typically entity.meta)

    Returns:
        New metadata dict with styling functions applied
    """
    # Sort by priority (lower numbers first)
    stylers = sorted(_metadata_stylers, key=lambda x: x.priority)
    active_tags = context.style_tags

    # Chain functions - output of one becomes input to next
    result = base_metadata
    for reg in stylers:
        # Skip if format filter is set and doesn't match
        if reg.formats is not None and context.output_format not in reg.formats:
            continue
        # Skip if tags specified but none match active tags
        if not _tags_match(reg.tags, active_tags):
            continue

        result = reg.func(entity, context, result)

    return result


def apply_entity_filters(entities: Sequence[Entity], context: StylingContext) -> list[Entity]:
    """Apply all matching entity filters in priority order (lower priority first).

    Filters are chained: each filter's output becomes the next filter's input.
    This allows complex filtering by composing simple filters.

    Args:
        entities: Sequence of entities to filter
        context: Styling context

    Returns:
        Filtered list of entities
    """
    # Sort by priority (lower numbers first - filters chain in order)
    funcs = sorted(_filter_entity_funcs, key=lambda x: x.priority)
    active_tags = context.style_tags

    # Chain all matching filters
    result: list[Entity] = list(entities)
    for reg in funcs:
        # Skip if format filter is set and doesn't match
        if reg.formats is not None and context.output_format not in reg.formats:
            continue
        # Skip if tags specified but none match active tags
        if not _tags_match(reg.tags, active_tags):
            continue

        # Apply filter (output becomes input for next filter)
        result = reg.func(result, context)

    return result


def apply_task_grouping(
    entities: Sequence[Entity], context: StylingContext
) -> dict[str | None, list[Entity]]:
    """Apply highest-priority grouping function, or return {None: entities} if none registered.

    Only the highest-priority grouping function that matches the output format is applied.

    Args:
        entities: List of entities to group
        context: Styling context

    Returns:
        Dict mapping section names (or None) to entity lists
    """
    # Sort by priority (higher numbers first for grouping - highest priority wins)
    funcs = sorted(_group_tasks_funcs, key=lambda x: x.priority, reverse=True)
    active_tags = context.style_tags

    # Find and apply highest priority function that matches format and tags
    for reg in funcs:
        # Skip if format filter is set and doesn't match
        if reg.formats is not None and context.output_format not in reg.formats:
            continue
        # Skip if tags specified but none match active tags
        if not _tags_match(reg.tags, active_tags):
            continue

        # Apply this function and return
        return reg.func(entities, context)

    # No grouping function registered or matched - return single group
    return {None: list(entities)}


def apply_task_sorting(entities: Sequence[Entity], context: StylingContext) -> list[Entity]:
    """Apply highest-priority sorting function, or return entities unchanged if none registered.

    Only the highest-priority sorting function that matches the output format is applied.

    Args:
        entities: List of entities from a single group to sort
        context: Styling context

    Returns:
        Sorted list of entities
    """
    # Sort by priority (higher numbers first for sorting - highest priority wins)
    funcs = sorted(_sort_tasks_funcs, key=lambda x: x.priority, reverse=True)
    active_tags = context.style_tags

    # Find and apply highest priority function that matches format and tags
    for reg in funcs:
        # Skip if format filter is set and doesn't match
        if reg.formats is not None and context.output_format not in reg.formats:
            continue
        # Skip if tags specified but none match active tags
        if not _tags_match(reg.tags, active_tags):
            continue

        # Apply this function and return
        return reg.func(entities, context)

    # No sorting function registered or matched - return entities unchanged
    return list(entities)


# ============================================================================
# StylingContext Implementation
# ============================================================================


class _StylingContextImpl:
    """Internal implementation of StylingContext protocol."""

    def __init__(
        self,
        feature_map: FeatureMap,
        output_format: str | None = None,
        config: dict[str, Any] | None = None,
        style_tags: set[str] | None = None,
    ):
        self._feature_map = feature_map
        self._output_format = output_format
        self._config = config or {}
        self._style_tags = style_tags or set()
        self._metadata_cache: dict[str, list[str]] = {}
        self._transitive_requires_cache: dict[str, set[str]] = {}
        self._transitive_enables_cache: dict[str, set[str]] = {}
        self._leaf_entities: set[str] | None = None
        self._root_entities: set[str] | None = None

    @property
    def output_format(self) -> str | None:
        """Output format being generated ('markdown', 'docx', 'gantt', etc.)."""
        return self._output_format

    @property
    def style_tags(self) -> set[str]:
        """Active style tags for filtering styling functions."""
        return self._style_tags

    def get_entity(self, entity_id: str) -> Entity | None:
        """Get entity by ID, or None if not found."""
        return self._feature_map.get_entity_by_id(entity_id)  # type: ignore

    def get_all_entities(self) -> list[Entity]:
        """Get all entities in the graph."""
        return self._feature_map.entities  # type: ignore

    def get_entities_by_type(self, entity_type: str) -> list[Entity]:
        """Get all entities of a given type."""
        return self._feature_map.get_entities_by_type(entity_type)  # type: ignore

    def transitively_requires(self, entity_id: str) -> set[str]:
        """Get all entity IDs that this entity transitively depends on."""
        if entity_id not in self._transitive_requires_cache:
            result: set[str] = set()
            to_visit = [entity_id]
            visited: set[str] = set()

            while to_visit:
                current = to_visit.pop()
                if current in visited:
                    continue
                visited.add(current)

                entity = self._feature_map.get_entity_by_id(current)
                if entity:
                    for req_id in entity.requires_ids:
                        if req_id not in visited:
                            result.add(req_id)
                            to_visit.append(req_id)

            self._transitive_requires_cache[entity_id] = result

        return self._transitive_requires_cache[entity_id]

    def transitively_enables(self, entity_id: str) -> set[str]:
        """Get all entity IDs that this entity transitively enables."""
        if entity_id not in self._transitive_enables_cache:
            result: set[str] = set()
            to_visit = [entity_id]
            visited: set[str] = set()

            while to_visit:
                current = to_visit.pop()
                if current in visited:
                    continue
                visited.add(current)

                entity = self._feature_map.get_entity_by_id(current)
                if entity:
                    for enabled_id in entity.enables_ids:
                        if enabled_id not in visited:
                            result.add(enabled_id)
                            to_visit.append(enabled_id)

            self._transitive_enables_cache[entity_id] = result

        return self._transitive_enables_cache[entity_id]

    def get_leaf_entities(self) -> set[str]:
        """Get entity IDs that don't enable anything (graph leaves)."""
        if self._leaf_entities is None:
            self._leaf_entities = {
                entity.id for entity in self._feature_map.entities if not entity.enables_ids
            }
        return self._leaf_entities

    def get_root_entities(self) -> set[str]:
        """Get entity IDs that don't require anything (graph roots)."""
        if self._root_entities is None:
            self._root_entities = {
                entity.id for entity in self._feature_map.entities if not entity.requires_ids
            }
        return self._root_entities

    def collect_metadata_values(self, key: str) -> list[str]:
        """Collect all unique values for a metadata key across all entities."""
        if key not in self._metadata_cache:
            values: set[str] = set()
            for entity in self._feature_map.entities:
                if key in entity.meta:
                    values.add(str(entity.meta[key]))
            self._metadata_cache[key] = sorted(values)
        return self._metadata_cache[key]


def create_styling_context(
    feature_map: FeatureMap,
    output_format: str | None = None,
    config: dict[str, Any] | None = None,
    style_tags: set[str] | None = None,
) -> StylingContext:
    """Create a styling context for the given feature map.

    Args:
        feature_map: The feature map to create context for
        output_format: Optional output format identifier ('markdown', 'docx', 'gantt', etc.)
        config: Optional configuration dict (accessible to styling functions via context._config)
        style_tags: Optional set of active style tags for filtering styling functions

    Returns:
        A StylingContext that can be used by styling functions
    """
    return _StylingContextImpl(feature_map, output_format, config, style_tags)  # type: ignore


# ============================================================================
# Public API Exports
# ============================================================================

__all__ = [
    # Decorators
    "style_node",
    "style_edge",
    "style_label",
    "style_task",
    "style_metadata",
    "group_tasks",
    "sort_tasks",
    "filter_entity",
    # Protocols
    "Entity",
    "Link",
    "StylingContext",
    "NodeStyle",
    "EdgeStyle",
    "TaskStyle",
    # Utility functions
    "sequential_hue",
    "contrast_text_color",
    # Context creation
    "create_styling_context",
    # Internal functions (for mouc internal use)
    "apply_node_styles",
    "apply_edge_styles",
    "apply_label_styles",
    "apply_task_styles",
    "apply_metadata_styles",
    "apply_task_grouping",
    "apply_task_sorting",
    "apply_entity_filters",
    "clear_registrations",
]
