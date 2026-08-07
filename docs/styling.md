# Mouc Styling System

The Mouc styling system allows you to customize the appearance of graph visualizations and markdown output by providing Python functions that compute styles based on entity data and graph structure.

## Table of Contents

- [Quick Start](#quick-start)
- [Basic Usage](#basic-usage)
- [Writing Style Functions](#writing-style-functions)
  - [Grouping (Gantt Sections and Graph Clusters)](#grouping-gantt-sections-and-graph-clusters)
  - [Entity Filtering](#entity-filtering)
- [API Reference](#api-reference)
- [Tag-Based Filtering](#tag-based-filtering)
- [Examples](#examples)
- [Best Practices](#best-practices)

## Quick Start

1. Create a Python file with your styling functions:

```python
# my_styles.py
from mouc.styling import *

@style_node
def color_by_type(entity, context):
    """Set colors based on entity type."""
    colors = {
        'capability': '#e3f2fd',
        'user_story': '#e8f5e9',
        'outcome': '#fff9c4'
    }
    return {'fill_color': colors.get(entity.type, 'white')}
```

2. Use it with mouc commands:

```bash
mouc graph --style-file ./my_styles.py
mouc doc --style-file ./my_styles.py
mouc gantt --style-file ./my_styles.py
```

## Basic Usage

### Loading Style Modules

There are two ways to load styling functions:

```bash
# From a Python module (must be on PYTHONPATH)
mouc graph --style-module myproject.docs.styling

# From a file path (no PYTHONPATH dependency)
mouc graph --style-file ./my_styles.py

# Same options work for markdown and gantt chart generation
mouc doc --style-module myproject.docs.styling
mouc doc --style-file ./my_styles.py
mouc gantt --style-module myproject.docs.styling
mouc gantt --style-file ./my_styles.py
```

### Style Module Structure

A style module is a Python file that imports from `mouc.styling` and defines decorated functions:

```python
from mouc.styling import *

@style_node
def my_node_styler(entity, context):
    """Style nodes in graph visualizations."""
    return {'fill_color': '#ff0000'}

@style_edge
def my_edge_styler(from_id, to_id, edge_type, context):
    """Style edges in graph visualizations."""
    return {'color': '#666666', 'style': 'dashed'}

@style_task
def my_task_styler(entity, context):
    """Style tasks in gantt charts."""
    return {'tags': ['done']}

@style_label
def my_label_styler(entity, context):
    """Customize markdown labels."""
    return f'[{entity.type.upper()}]'
```

## Writing Style Functions

### Node Styling

Node styling functions control how entities appear in graphs:

```python
@style_node
def basic_node_styling(entity, context):
    """Style nodes based on entity properties."""
    style = {}

    # Shape based on type
    shapes = {
        'capability': 'box',
        'user_story': 'oval',
        'outcome': 'diamond'
    }
    style['shape'] = shapes.get(entity.type, 'oval')

    # Color based on tags
    if 'critical' in entity.tags:
        style['border_color'] = '#ff0000'
        style['border_width'] = 3

    return style
```

Available node attributes:
- `shape`: `'oval'`, `'box'`, `'diamond'`, `'hexagon'`, etc.
- `fill_color`: CSS color or hex string
- `text_color`: CSS color or hex string
- `border_color`: CSS color or hex string
- `border_width`: integer
- `fontsize`: integer
- `fontname`: string

### Priority Ordering

Multiple style functions are applied in priority order (lower numbers first). Later functions override earlier ones for conflicting attributes:

```python
@style_node(priority=10)
def base_styling(entity, context):
    """Apply base colors (runs first)."""
    return {'fill_color': 'lightblue'}

@style_node(priority=20)
def special_highlighting(entity, context):
    """Override colors for special entities (runs second)."""
    if 'critical' in entity.tags:
        return {'fill_color': 'red'}  # Overrides base color
    return {}
```

### Format Filtering

Style functions can be restricted to specific output formats using the `formats` parameter. This allows you to apply different styling based on whether you're generating graphs, markdown, docx, or gantt charts:

```python
@style_metadata(formats=['docx'])
def filter_docx_metadata(entity, context, metadata):
    """Remove verbose fields from docx output."""
    result = metadata.copy()
    result.pop('internal_notes', None)
    return result

@style_metadata(formats=['markdown'])
def enhance_markdown_metadata(entity, context, metadata):
    """Add formatted links for markdown output."""
    result = metadata.copy()
    if 'jira' in metadata:
        result['Link'] = f"[{metadata['jira']}](https://jira.example.com/{metadata['jira']})"
    return result

@style_label(formats=['markdown', 'docx'])
def custom_label_for_docs(entity, context):
    """Custom labels only for documentation, not graphs."""
    return f"[{entity.type.title()}]"
```

**Available format identifiers:**
- `'markdown'` - Markdown documentation output
- `'docx'` - Word document output
- `'graph'` - Graph visualizations
- `'gantt'` - Gantt chart output

**Format detection in context:**

You can also check the current format within a styler using `context.output_format`:

```python
@style_metadata(formats=['markdown', 'docx'])
def conditional_metadata(entity, context, metadata):
    """Apply different logic based on format."""
    result = metadata.copy()

    if context.output_format == 'markdown':
        # Markdown-specific formatting
        result['Link'] = f"[{metadata.get('jira')}](https://...)"
    elif context.output_format == 'docx':
        # DOCX keeps it simple - hyperlinks handled by backend
        result['Jira'] = metadata.get('jira')

    return result
```

This approach combines declarative filtering (via `formats` parameter) with imperative logic (via `context.output_format`) for maximum flexibility.

### Edge Styling

Edge styling functions control how relationships appear:

```python
@style_edge
def edge_styling(from_id, to_id, edge_type, context):
    """Style edges based on relationship type."""
    if edge_type == 'requires':
        return {
            'color': '#000000',
            'style': 'solid',
            'penwidth': 2
        }
    else:  # enables
        return {
            'color': '#666666',
            'style': 'dashed',
            'penwidth': 1
        }
```

Available edge attributes:
- `color`: CSS color or hex string
- `style`: `'solid'`, `'dashed'`, `'dotted'`
- `penwidth`: integer
- `arrowhead`: `'normal'`, `'none'`, `'vee'`, etc.

Edge types:
- `'requires'`: Entity depends on another
- `'enables'`: Entity enables another (reverse of requires)

### Label Styling

Label styling functions control markdown output labels:

```python
@style_label
def custom_labels(entity, context):
    """Customize how entities are labeled in markdown."""
    # Show timeframe in label
    if 'timeframe' in entity.meta:
        return f'[{entity.meta["timeframe"]}]'

    # Hide label for specific entities
    if entity.type == 'capability':
        return ''  # Empty string hides the label

    # Use default for others
    return None  # None means use default label
```

Multiple label functions are applied in priority order. The last non-`None` result is used.

**Return values:**
- Return a string to use as the label (e.g., `"[Custom]"`)
- Return `""` (empty string) to hide the label entirely
- Return `None` to use the default label (or let the next styler decide)

### Task Styling (Gantt Charts)

Task styling functions control how tasks appear in Gantt charts using both predefined tags and custom CSS colors:

```python
@style_task
def status_based_styling(entity, context):
    """Style tasks based on their status."""
    status = entity.meta.get('status')
    if status == 'done':
        return {'tags': ['done']}
    elif status == 'critical':
        return {'tags': ['crit']}
    return {'tags': ['active']}

@style_task(priority=20)
def color_by_team(entity, context):
    """Apply custom colors by team."""
    team = entity.meta.get('team')
    colors = {
        'platform': '#4287f5',
        'backend': '#42f554',
        'frontend': '#f54242'
    }
    if team in colors:
        return {'fill_color': colors[team]}
    return {}
```

#### Available Task Tags

Mermaid gantt tags provide predefined visual styles:
- `'done'`: Completed tasks (displayed in green)
- `'crit'`: Critical path tasks (displayed in red)
- `'active'`: In-progress tasks (displayed in blue)
- `'milestone'`: Single-point-in-time events

#### Available CSS Properties

Custom colors are applied via Mermaid's `themeCSS` configuration:
- `'fill_color'`: Task bar fill color (CSS color value)
- `'stroke_color'`: Task bar border color (CSS color value)
- `'text_color'`: Task text color (CSS color value)

CSS colors are generated automatically in the YAML frontmatter as:
```yaml
config:
    themeCSS: "
        #taskId { fill: #4287f5; stroke: #00ff00; color: #000000 }
    "
```

#### Available Task Attributes

- `tags`: List of Mermaid task tags
- `section`: Optional section name for grouping (currently not used by generator)
- `fill_color`: CSS color for task bar fill
- `stroke_color`: CSS color for task bar border
- `text_color`: CSS color for task text

#### Tag Merging

Unlike node/edge styling where attributes are replaced, `tags` from multiple task stylers are **merged together**. This allows different stylers to add tags independently:

```python
@style_task(priority=10)
def mark_high_priority(entity, context):
    """Mark high priority tasks as critical."""
    if entity.meta.get('priority') == 'high':
        return {'tags': ['crit']}
    return {}

@style_task(priority=20)
def mark_blocking_outcomes(entity, context):
    """Mark tasks that block outcomes."""
    enabled = context.transitively_enables(entity.id)
    outcomes = [e for e in enabled
                if context.get_entity(e) and context.get_entity(e).type == 'outcome']
    if outcomes and entity.meta.get('status') != 'done':
        # This tag will be merged with tags from previous stylers
        return {'tags': ['active']}
    return {}
```

#### Default Behavior

If no task stylers are registered, gantt charts use the default behavior:
- Tasks with `status: done` are marked with the `done` tag
- Tasks that are late (past deadline) are marked with the `crit` tag
- Unassigned tasks are marked with the `active` tag

### Grouping (Gantt Sections and Graph Clusters)

Grouping functions return a dict mapping group names to entity lists. The same function drives **gantt sections** and **graph `subgraph cluster_*` boxes**:

```python
from mouc.styling import group_tasks

@group_tasks(formats=['graph'])
def cluster_by_repo(entities, context):
    """Cluster graph nodes by their home repository."""
    groups = {}
    unclustered = []
    for entity in entities:
        repo = entity.meta.get('repo')
        if repo:
            groups.setdefault(repo, []).append(entity)
        else:
            unclustered.append(entity)
    result = dict(sorted(groups.items()))  # dict order = cluster order
    if unclustered:
        result[None] = unclustered  # rendered outside all clusters
    return result
```

- Keys are group names; the `None` key means "no gantt section" / "no graph cluster" (those nodes render at the top level of the graph, outside every cluster box).
- Dict insertion order controls section/cluster display order.
- Entities omitted from the returned dict are omitted from the output.
- Only one grouping function is active: the highest-priority registration matching the output format and active style tags.
- Scope with `formats=['gantt']` or `formats=['graph']`; a function registered without `formats` affects **both** gantt sections and graph clusters.
- The `--view timeline` graph view has its own timeframe clusters and ignores grouping functions.

For simple field-based graph clusters there is a CLI shortcut that registers a built-in grouping function for you (priority 5, so the functions above override it):

```bash
mouc graph feature_map.yaml --cluster-by meta.repo
```

`--cluster-by` takes a dotted entity field path. List values cluster by their first entry, entities without a value render outside all clusters, and a value that is neither missing nor a scalar (a dict, set, or tuple) is an error.

When a grouping function outranks the shortcut, `--cluster-by` is inert: the flag's path is not resolved at all, so it produces neither clusters, warnings, nor errors.

### Entity Filtering

Entity filtering functions control which entities appear in the output. Filters work across all output types (documents, graphs, and gantt charts) and run before any organization, grouping, or sorting logic:

```python
@filter_entity
def filter_incomplete(entities, context):
    """Only show incomplete tasks."""
    return [e for e in entities if e.meta.get('status') != 'done']

@filter_entity(formats=['gantt'])
def filter_q1_only(entities, context):
    """Only show Q1 items in gantt charts."""
    return [e for e in entities if e.meta.get('timeframe', '').startswith('2025-Q1')]
```

#### Filter Chaining

Unlike grouping and sorting (where highest priority wins), **all filters are applied in sequence** in priority order (lower priority first):

```python
@filter_entity(priority=5)
def filter_by_type(entities, context):
    """First, keep only capabilities and user stories."""
    return [e for e in entities if e.type in ('capability', 'user_story')]

@filter_entity(priority=10)
def filter_by_priority(entities, context):
    """Then, keep only high priority items from the filtered set."""
    return [e for e in entities if e.meta.get('priority', 0) > 5]
```

In this example, both filters run in sequence:
1. First filter runs (priority 5): removes outcomes
2. Second filter runs (priority 10): removes low priority items from the remaining entities

#### Format Targeting

Filters can be targeted to specific output formats:

```python
@filter_entity(formats=['gantt'])
def gantt_only_filter(entities, context):
    """This filter only applies to gantt charts."""
    return [e for e in entities if e.meta.get('status') != 'done']

@filter_entity(formats=['graph', 'markdown'])
def doc_and_graph_filter(entities, context):
    """This filter applies to graphs and markdown, but not gantt."""
    return [e for e in entities if 'archived' not in e.tags]

@filter_entity()  # No formats = applies to all outputs
def global_filter(entities, context):
    """This filter applies to all output types."""
    return [e for e in entities if e.meta.get('deleted') != True]
```

#### Pipeline Order

Entity filters run **before** organization, grouping, and sorting:

```
Feature Map → Filter → Group/Sort → Render
```

This means:
- Filtered entities are completely removed from the output
- TOC and sections only include filtered entities
- Dependency relationships in graphs only show filtered entities

## API Reference

### StylingContext Methods

The `context` parameter provides graph analysis methods:

#### Entity Queries

```python
# Get entity by ID
entity = context.get_entity('cap1')

# Get all entities
all_entities = context.get_all_entities()

# Get entities by type
capabilities = context.get_entities_by_type('capability')
```

#### Graph Traversal

```python
# Get all entities this entity transitively depends on
dependencies = context.transitively_requires('outcome1')

# Get all entities this entity transitively enables
enabled = context.transitively_enables('cap1')

# Get leaf entities (no outgoing edges)
leaves = context.get_leaf_entities()

# Get root entities (no incoming edges)
roots = context.get_root_entities()
```

#### Metadata Collection

```python
# Collect all unique values for a metadata key
timeframes = context.collect_metadata_values('timeframe')
# Returns: ['Q1 2025', 'Q2 2025', 'Q3 2025']
```

#### Output Format

```python
# Get the current output format being generated
format = context.output_format
# Returns: 'markdown', 'docx', 'graph', 'gantt', or None

# Use in conditional logic
if context.output_format == 'markdown':
    # Markdown-specific styling
    pass
elif context.output_format == 'docx':
    # DOCX-specific styling
    pass
```

#### Active Style Tags

```python
# Get active style tags for conditional logic
tags = context.style_tags
# Returns: set[str] of active tags

# Check if a specific tag is active
if 'detailed' in context.style_tags:
    # Include extra detail
    pass
```

### Entity Properties

#### Schedule Annotations

When using `mouc doc --schedule` or `mouc doc --lock-file`, entities are populated with schedule annotations:

```python
# Access schedule annotations in your styling functions
schedule = entity.annotations.get('schedule')

if schedule:
    # Computed dates from forward pass
    start: date | None = schedule.estimated_start
    end: date | None = schedule.estimated_end

    # Deadline from backward pass (may differ from manual end_before)
    deadline: date | None = schedule.computed_deadline

    # Boolean indicating if task is late
    late: bool = schedule.deadline_violated

    # Resource assignments: list of (resource_name, allocation) tuples
    resources: list[tuple[str, float]] = schedule.resource_assignments

    # Whether resources were auto-assigned vs manual
    auto_assigned: bool = schedule.resources_were_computed

    # Whether task had fixed dates (start_date/end_date, not computed)
    fixed: bool = schedule.was_fixed
```

**Important:** Schedule annotations are **only available** when running `mouc doc --schedule`, `mouc doc --lock-file`, or `mouc gantt`. They are not available in the YAML metadata by default.

#### Injecting Schedule Data into Markdown

To display schedule information in markdown output, use `@style_metadata()` functions:

```python
from mouc.styling import style_metadata

@style_metadata()
def inject_schedule_to_markdown(entity, context, metadata):
    """Add schedule annotations to markdown metadata table."""
    schedule = entity.annotations.get('schedule')
    if not schedule or schedule.was_fixed:
        return metadata  # Skip fixed-date tasks, return unchanged

    # Copy metadata and add computed dates
    result = metadata.copy()
    if schedule.estimated_start:
        result['Estimated Start'] = str(schedule.estimated_start)
    if schedule.estimated_end:
        result['Estimated End'] = str(schedule.estimated_end)

    # Highlight deadline violations
    if schedule.deadline_violated:
        result['⚠️ Status'] = 'DEADLINE VIOLATED'

    return result  # Return new dict, input not mutated
```

**Key points:**
- Metadata styling functions are **chained** - output of one becomes input to next
- Always return a **new** dict (use `.copy()`) - never mutate the input
- Return the input unchanged if no modifications needed

See `examples/schedule_markdown_style.py` for a complete example.

### Utility Functions

#### sequential_hue()

Generate colors for sequential categorical values:

```python
timeframes = ['Q1', 'Q2', 'Q3', 'Q4']
color = sequential_hue(
    'Q2',                        # Value to color
    timeframes,                  # All possible values
    hue_range=(120, 230),       # HSL hue range in degrees (0-360)
    lightness_range=(95, 75),   # HSL lightness range (0-100)
    saturation=60               # HSL saturation (0-100)
)
# Returns: '#9df4dd' (RGB hex, ready for Graphviz)
```

#### contrast_text_color()

Compute readable text color for a background:

```python
bg = '#ff0000'
fg = contrast_text_color(bg)  # Returns '#ffffff' or '#000000'

# Works with HSL colors too
bg = sequential_hue('Q2', timeframes)
fg = contrast_text_color(bg)
```

## Tag-Based Filtering

Style functions can be conditionally enabled using tags. This allows a single styling module to serve multiple report types by selectively activating functions.

### Declaring Tags on Functions

Add the `tags` parameter to any decorator to make the function tag-gated:

```python
@style_node(tags=['detailed'])
def show_extra_info(entity, context):
    """Only runs when 'detailed' tag is active."""
    return {'fontsize': 14}

@style_task(tags=['color-by-team', 'team-view'])
def team_colors(entity, context):
    """Runs when EITHER 'color-by-team' OR 'team-view' is active."""
    team = entity.meta.get('team')
    colors = {'platform': '#4287f5', 'backend': '#42f554'}
    return {'fill_color': colors.get(team, 'white')}

@filter_entity(tags=['hide-completed'])
def filter_done(entities, context):
    """Filter only runs when 'hide-completed' tag is active."""
    return [e for e in entities if e.meta.get('status') != 'done']
```

### Tag Matching Logic

- **`tags=None`** (default): Function always runs (backwards compatible)
- **`tags=['a', 'b']`**: Function runs if **ANY** positive tag matches active tags (OR logic)
- **`tags=['!a']`**: Negated tags - function runs only when tag `a` is **NOT** active
- **`tags=['!a', '!b']`**: Multiple negations - function runs only when **ALL** negated tags are absent (AND logic)
- **`tags=['a', '!b']`**: Mixed - function runs when `a` is active **AND** `b` is not active

**Negation examples:**

```python
@style_node(tags=['!detailed'])
def compact_view(entity, context):
    """Only runs when 'detailed' tag is NOT active."""
    return {'fontsize': 10}

@style_node(tags=['verbose', '!executive'])
def detailed_tech_view(entity, context):
    """Runs when 'verbose' is active AND 'executive' is NOT active."""
    return {'fontsize': 14, 'border_width': 2}
```

### Activating Tags

#### Via CLI

Use `--style-tags` with comma-separated values:

```bash
mouc gantt feature_map.yaml --style-tags detailed,color-by-team
mouc doc feature_map.yaml --style-tags executive-summary
mouc graph feature_map.yaml --style-tags hide-completed
```

#### Via Config File

Add `style_tags` to `mouc_config.yaml`:

```yaml
# mouc_config.yaml
style_tags:
  - detailed
  - color-by-team

resources:
  # ... resource config
```

CLI tags and config tags are **merged** together.

### Combining Tags with Formats

Tags work alongside the existing `formats` parameter. Both must match for a function to run:

```python
@style_task(formats=['gantt'], tags=['detailed'])
def detailed_gantt_styling(entity, context):
    """Only runs for gantt output AND when 'detailed' tag is active."""
    return {'tags': ['active']}
```

### Checking Tags in Functions

Access active tags via `context.style_tags`:

```python
@style_node
def conditional_styling(entity, context):
    """Use tags for conditional logic within a function."""
    if 'verbose' in context.style_tags:
        return {'fontsize': 16, 'border_width': 3}
    return {'fontsize': 12}
```

## Examples

### Example 1: Color by Timeframe

```python
from mouc.styling import *

@style_node
def timeframe_colors(entity, context):
    """Color entities based on their timeframe metadata."""
    if 'timeframe' not in entity.meta:
        return {}

    # Collect all timeframes for consistent coloring
    timeframes = context.collect_metadata_values('timeframe')

    # Generate color for this timeframe
    bg_color = sequential_hue(
        entity.meta['timeframe'],
        timeframes,
        hue_range=(120, 230),      # Green to blue
        lightness_range=(95, 75)   # Light to darker
    )

    # Ensure text is readable
    text_color = contrast_text_color(bg_color)

    return {
        'fill_color': bg_color,
        'text_color': text_color
    }
```

### Example 2: Highlight Critical Path

```python
from mouc.styling import *

@style_node(priority=20)
def highlight_critical_path(entity, context):
    """Highlight entities on the critical path to company priorities."""
    # Find all outcomes tagged as company priorities
    priority_outcomes = [
        e for e in context.get_entities_by_type('outcome')
        if 'company_priority' in e.tags
    ]

    # Check if this entity enables any priority outcomes
    enabled = context.transitively_enables(entity.id)
    for outcome in priority_outcomes:
        if outcome.id in enabled:
            return {
                'border_color': '#ff0000',
                'border_width': 3
            }

    return {}
```

### Example 3: Shape by Type

```python
from mouc.styling import *

@style_node
def shapes_by_type(entity, context):
    """Use different shapes for different entity types."""
    shapes = {
        'capability': 'box',
        'user_story': 'oval',
        'outcome': 'diamond'
    }
    return {'shape': shapes.get(entity.type, 'oval')}
```

### Example 4: Team-Based Coloring

```python
from mouc.styling import *

@style_node
def color_by_team(entity, context):
    """Color entities based on owning team."""
    if 'owner' not in entity.meta:
        return {}

    team_colors = {
        'frontend': '#e3f2fd',
        'backend': '#e8f5e9',
        'infrastructure': '#fff9c4',
        'data': '#fce4ec'
    }

    owner = entity.meta['owner']
    return {'fill_color': team_colors.get(owner, 'white')}
```

### Example 5: Custom Markdown Labels

```python
from mouc.styling import *

@style_label
def show_milestone_labels(entity, context):
    """Show which milestones this entity enables."""
    # Find all outcomes this entity transitively enables
    enabled_ids = context.transitively_enables(entity.id)

    # Filter to milestone outcomes
    milestones = [
        context.get_entity(eid)
        for eid in enabled_ids
        if context.get_entity(eid) and
           context.get_entity(eid).type == 'outcome' and
           'milestone' in context.get_entity(eid).tags
    ]

    if milestones:
        names = [m.name for m in milestones]
        return ' → ' + ', '.join(names)

    return None  # Use default label
```

### Example 6: Schedule Annotations in Markdown

Display computed schedule information in markdown documentation:

```python
from mouc.styling import *

@style_metadata()
def add_schedule_to_markdown(entity, context, metadata):
    """Inject schedule annotations into markdown metadata table.

    Run with: mouc doc --schedule --style-file my_styles.py
    Or with:  mouc doc --lock-file schedule.lock --style-file my_styles.py
    """
    schedule = entity.annotations.get('schedule')
    if not schedule or schedule.was_fixed:
        return metadata  # No annotations or fixed dates - return unchanged

    # Copy metadata and add computed fields
    result = metadata.copy()

    # Add estimated dates
    if schedule.estimated_start:
        result['📅 Estimated Start'] = str(schedule.estimated_start)
    if schedule.estimated_end:
        result['📅 Estimated End'] = str(schedule.estimated_end)

    # Show computed deadline if it exists
    if schedule.computed_deadline:
        result['⏰ Deadline'] = str(schedule.computed_deadline)

    # Warn about deadline violations
    if schedule.deadline_violated:
        result['⚠️  Status'] = 'LATE (deadline exceeded)'

    # Show resource assignments
    if schedule.resource_assignments:
        resources = ', '.join(
            f'{name}:{alloc}' for name, alloc in schedule.resource_assignments
        )
        suffix = ' (auto-assigned)' if schedule.resources_were_computed else ''
        result['👥 Resources'] = resources + suffix

    return result  # Return new dict with annotations added
```

See `examples/schedule_markdown_style.py` for a complete working example.

### Example 7: Gantt Chart Task Styling

```python
from mouc.styling import *

@style_task(priority=10)
def style_by_status_and_priority(entity, context):
    """Style gantt tasks based on status and priority using tags."""
    tags = []

    # Check completion status first
    status = entity.meta.get('status')
    if status == 'done':
        tags.append('done')
        return {'tags': tags}

    # Check priority for incomplete tasks
    priority = entity.meta.get('priority')
    if priority == 'high':
        tags.append('crit')
    elif priority == 'medium':
        tags.append('active')

    return {'tags': tags}

@style_task(priority=20)
def color_by_team(entity, context):
    """Apply custom colors by team ownership."""
    team = entity.meta.get('team')
    colors = {
        'platform': '#4287f5',
        'backend': '#42f554',
        'frontend': '#f54242'
    }
    if team in colors:
        return {'fill_color': colors[team]}
    return {}

@style_task(priority=30)
def highlight_blocking_tasks(entity, context):
    """Mark tasks that block outcomes with distinct styling."""
    # Find all outcomes this entity transitively enables
    enabled = context.transitively_enables(entity.id)
    enabled_outcomes = [
        e for e in enabled
        if context.get_entity(e) and context.get_entity(e).type == 'outcome'
    ]

    # If this blocks outcomes and isn't done, add thick border
    if enabled_outcomes and entity.meta.get('status') != 'done':
        return {'stroke_color': '#ff0000', 'tags': ['crit']}

    return {}
```

### Example 8: Complex Multi-Function Styling

```python
from mouc.styling import *

# Base layer: default colors and shapes
@style_node(priority=10)
def base_styling(entity, context):
    """Apply base styling to all entities."""
    type_styles = {
        'capability': {'shape': 'box', 'fill_color': '#e3f2fd'},
        'user_story': {'shape': 'oval', 'fill_color': '#e8f5e9'},
        'outcome': {'shape': 'diamond', 'fill_color': '#fff9c4'}
    }
    return type_styles.get(entity.type, {})

# Middle layer: timeframe coloring (overrides base colors)
@style_node(priority=20)
def timeframe_overlay(entity, context):
    """Override colors based on timeframe."""
    if 'timeframe' in entity.meta:
        timeframes = context.collect_metadata_values('timeframe')
        return {
            'fill_color': sequential_hue(
                entity.meta['timeframe'],
                timeframes,
                hue_range=(200, 280)
            )
        }
    return {}

# Top layer: critical highlighting (overrides everything)
@style_node(priority=30)
def critical_overlay(entity, context):
    """Highlight critical entities with borders."""
    if 'critical' in entity.tags:
        return {
            'border_color': '#ff0000',
            'border_width': 3
        }
    return {}

# Edge styling
@style_edge
def edge_styling(from_id, to_id, edge_type, context):
    """Style edges based on type."""
    return {
        'color': '#666666',
        'style': 'dashed' if edge_type == 'enables' else 'solid'
    }

# Label styling
@style_label
def label_styling(entity, context):
    """Show custom labels for critical entities."""
    if 'critical' in entity.tags:
        return '[🔥 CRITICAL]'
    return None  # Use default label for non-critical entities
```

### Example 9: Entity Filtering

Control which entities appear in output across all formats:

```python
from mouc.styling import *

@filter_entity(formats=['gantt'])
def hide_completed_in_gantt(entities, context):
    """Don't show completed tasks in gantt charts."""
    return [e for e in entities if e.meta.get('status') != 'done']

@filter_entity(priority=5)
def filter_by_timeframe(entities, context):
    """Only show Q1 and Q2 entities."""
    return [
        e for e in entities
        if e.meta.get('timeframe', '').startswith(('2025-Q1', '2025-Q2'))
    ]

@filter_entity(priority=10)
def filter_backend_only(entities, context):
    """Further filter to backend work only (runs after timeframe filter)."""
    return [e for e in entities if 'backend' in e.tags]
```

This example demonstrates:
- Format-specific filtering (gantt only)
- Chained filters (timeframe → backend)
- Priority ordering (lower priority runs first)

## Best Practices

### 1. Use Priority Layering

Structure your styling with clear priority layers:
- Priority 10: Base styling (shapes, default colors)
- Priority 20: Thematic overlays (timeframes, teams)
- Priority 30+: Highlights and exceptions (critical items, blockers)

### 2. Return Empty Dicts

When a style function doesn't apply, return an empty dict:

```python
@style_node
def my_styler(entity, context):
    if some_condition:
        return {'fill_color': 'red'}
    return {}  # Don't return None
```

### 3. Cache Expensive Queries

The context caches most queries, but if you do expensive computation, consider doing it once:

```python
@style_node
def optimized_styling(entity, context):
    # This is cached by context
    timeframes = context.collect_metadata_values('timeframe')

    # Avoid repeated lookups in loops
    if hasattr(optimized_styling, '_cache'):
        expensive_data = optimized_styling._cache
    else:
        expensive_data = compute_expensive_data(context)
        optimized_styling._cache = expensive_data

    return {'fill_color': expensive_data[entity.id]}
```

### 4. Use Utility Functions

Leverage built-in utilities for common tasks:

```python
# Good: Use sequential_hue for categorical values
@style_node
def good_colors(entity, context):
    values = context.collect_metadata_values('priority')
    return {
        'fill_color': sequential_hue(entity.meta['priority'], values)
    }

# Avoid: Manual color calculation
@style_node
def manual_colors(entity, context):
    # More error-prone
    priority = entity.meta['priority']
    if priority == 'high':
        color = '#ff0000'
    elif priority == 'medium':
        color = '#ffff00'
    else:
        color = '#00ff00'
    return {'fill_color': color}
```

### 5. Handle Missing Data Gracefully

Always check if metadata exists before using it:

```python
@style_node
def safe_styling(entity, context):
    # Good: Check before accessing
    if 'timeframe' in entity.meta:
        timeframes = context.collect_metadata_values('timeframe')
        return {
            'fill_color': sequential_hue(
                entity.meta['timeframe'],
                timeframes
            )
        }
    return {}
```

### 6. Keep Functions Focused

Each styling function should have a single responsibility:

```python
# Good: Separate concerns
@style_node(priority=10)
def base_colors(entity, context):
    return {'fill_color': 'lightblue'}

@style_node(priority=20)
def highlight_critical(entity, context):
    if 'critical' in entity.tags:
        return {'border_color': 'red'}
    return {}

# Avoid: Doing too much in one function
@style_node
def everything(entity, context):
    # This becomes hard to maintain
    if 'critical' in entity.tags:
        return {'fill_color': 'red', 'border_width': 3}
    elif 'timeframe' in entity.meta:
        return {'fill_color': calculate_color(entity)}
    else:
        return {'fill_color': 'lightblue'}
```

### 7. Test Your Styles

Test your styling functions independently:

```python
from mouc.styling import *
from mouc.models import Entity, FeatureMap, FeatureMapMetadata

# Create test data
entities = [
    Entity(
        type='capability',
        id='test_cap',
        name='Test',
        description='Test',
        tags=['critical'],
        meta={'timeframe': 'Q1'}
    )
]
feature_map = FeatureMap(
    metadata=FeatureMapMetadata(),
    entities=entities
)

# Create context and test
context = create_styling_context(feature_map)
result = my_styler(entities[0], context)
print(result)  # Verify expected output
```

### 8. Share and Reuse

Create reusable styling modules for your organization:

```python
# company_styles.py
"""Standard Mouc styling for Acme Corp."""
from mouc.styling import *

TEAM_COLORS = {
    'frontend': '#e3f2fd',
    'backend': '#e8f5e9',
    'infrastructure': '#fff9c4'
}

@style_node
def acme_base_styling(entity, context):
    """Standard Acme Corp entity styling."""
    # ...implementation...
```

Then use it across projects:

```bash
mouc graph --style-module company_styles
```
