# Mouc

A YAML-based dependency tracker and automatic scheduler for project roadmaps.

## What Mouc Does

Mouc takes a YAML file describing your work items and their dependencies, and produces:

- **Scheduled Gantt charts** - automatically computed from dependencies, deadlines, priorities, and resource constraints
- **Dependency graphs** - visualize what blocks what
- **Documentation** - Markdown or Word docs, Gantt charts, and Graphviz/SVG graphs describing your roadmap

The scheduler handles the tedious work of figuring out *when* things should happen. You define *what* needs to happen, what it depends on, who can work on it, priorities, and any deadlines. Mouc computes a schedule that respects all constraints.

## What Mouc Isn't

Mouc is not a full project management system. It doesn't have:

- A web UI for editing (it's YAML + CLI)
- Time tracking, budgets, or cost management
- Collaboration features (comments, notifications, assignments)
- Velocity tracking (though you could script this yourself; it's just YAML)

Mouc is for engineers and tech leads who want version-controlled roadmaps with real scheduling logic, not another GUI to babysit.

## Mouc vs. Other Tools

Mouc complements tools like Jira rather than replacing them. Use Jira for ticket tracking and team collaboration; use Mouc for dependency-aware scheduling and roadmap generation.

Key differences from typical PM tools:

- **Automatic scheduling**: Most tools (including Jira, even with plugins) require you to manually set dates and drag Gantt bars. Mouc computes dates automatically using a real scheduling algorithm.
- **YAML-first**: Your roadmap lives in version control. Review changes in PRs. No proprietary database.
- **Workflow expansion**: Define patterns like "design → signoff → implement → review" once, apply them to many items. The scheduler handles the phasing automatically.
- **Free and open source**: MIT licensed.

The outputs (Mermaid Gantt charts, Graphviz graphs, Markdown) render in GitHub, GitLab, standard doc tools, or any static site. Run Mouc in CI to publish current roadmaps automatically.

## Installation

```bash
uv pip install mouc   # recommended
# or
pip install mouc
```

> **Windows users:** upstream PyPI currently ships manylinux wheels only.
> This fork publishes prebuilt Windows x64 wheels in
> [Releases](https://github.com/mimadiule/mouc/releases).
> See [WINDOWS.md](WINDOWS.md) for Python-version compatibility,
> installation, verification, and how to rebuild the wheel with GitHub Actions.

## Quick Example

Create `feature_map.yaml`:

```yaml
metadata:
  version: 1.0

entities:
  database_layer:
    type: capability
    name: Database Abstraction Layer
    description: Core data access patterns
    meta:
      effort: "2w"
      resources: ["alice"]

  api_service:
    type: capability
    name: REST API Service
    description: Public API endpoints
    requires: [database_layer]
    meta:
      effort: "3w"
      resources: ["bob"]
      end_before: "2025-03-31"

  mobile_app:
    type: outcome
    name: Mobile App Launch
    requires: [api_service]
    links:
      - jira:MOBILE-100
```

Generate outputs:

```bash
# Scheduled Gantt chart
mouc gantt --start-date 2025-01-01 --output schedule.md

# Dependency graph
mouc graph --view all | dot -Tsvg -o deps.svg

# Documentation
mouc doc --output roadmap.md
```

The Gantt chart automatically schedules `database_layer` first, then `api_service` (after its dependency completes), and warns if the March 31 deadline can't be met.

## Core Concepts

### Entities and Dependencies

By default, Mouc provides three entity types:

- **Capabilities** - technical work
- **User Stories** - what others need from you
- **Outcomes** - business goals

You can define your own entity types in `mouc_config.yaml` (see [Configuration](docs/config.md#entity-types-section)).

Specify dependencies with `requires` (what this needs) or `enables` (what this unblocks):

```yaml
database_layer:
  enables: [api_service, batch_jobs]  # these need database_layer

api_service:
  requires: [database_layer]          # equivalent to above
```

There's no difference between using `enables` on the blocker or `requires` on the blocked; these are normalized to the same thing. Use what is most convenient.

### Scheduling

Add metadata to enable automatic scheduling:

```yaml
meta:
  effort: "2w"                    # how long (days, weeks, months)
  resources: ["alice", "bob"]     # who works on it
  end_before: "2025-03-31"        # hard deadline
  timeframe: "2025q1"             # target quarter/month/week
```

The scheduler uses a priority-based algorithm that:

- Respects dependencies (B waits for A if B requires A)
- Prevents resource conflicts (Alice can't do two things at once)
- Prioritizes by deadline urgency and task duration
- Propagates deadlines backward through dependency chains

See [docs/scheduling.md](docs/scheduling.md) for algorithm details including the bounded rollout feature for more-optimal decisions.

### Workflows

Workflows expand a single entity into multiple phases with proper dependencies:

```yaml
auth_redesign:
  type: capability
  name: Auth Redesign
  workflow: design_impl        # expands to design phase + implementation
  meta:
    effort: "2w"
```

This creates `auth_redesign_design` (floats freely) and `auth_redesign` (waits for design + signoff lag). Built-in workflows include `design_impl`, `impl_pr`, `full`, and `phased_rollout`. You can implement your own workflows with Python plugins.

See [docs/workflows.md](docs/workflows.md) for details.

### Resources

Define team members, availability, and assignment preferences:

```yaml
# mouc_config.yaml
resources:
  - name: alice
    dns_periods:                  # do-not-schedule periods
      - start: 2025-12-20
        end: 2025-12-31

groups:
  backend_team: [alice, bob, charlie]

default_resource: "*"             # auto-assign unassigned tasks
```

In your feature map:

```yaml
meta:
  resources: ["alice"]              # explicit
  resources: ["*"]                  # any available
  resources: ["alice|bob"]          # prefer alice, fall back to bob
  resources: ["backend_team"]       # anyone in the group
  resources: ["!john"]              # Anybody but john
```

See [docs/resources.md](docs/resources.md) for details.

### Jira Integration

Sync metadata from Jira issues:

```yaml
entities:
  auth_service:
    type: capability
    name: Auth Service
    links:
      - jira:AUTH-123           # pulls dates, status, assignee from Jira
```

```bash
mouc jira sync feature_map.yaml --dry-run   # preview changes
mouc jira sync feature_map.yaml --apply     # apply changes
```

The sync is read-only (Jira → Mouc) with configurable conflict resolution.

See [docs/jira.md](docs/jira.md) for setup and configuration.

## Commands

| Command | Description |
|---------|-------------|
| `mouc gantt` | Generate Mermaid Gantt chart with automatic scheduling |
| `mouc schedule` | Run scheduler and display or export results |
| `mouc compare` | Compare schedule scenarios (CSV diff with deltas) |
| `mouc report effort` | Generate effort report for a time range (CSV) |
| `mouc graph` | Generate Graphviz dependency graph |
| `mouc doc` | Generate Markdown or DOCX documentation |
| `mouc jira sync` | Sync metadata from Jira |
| `mouc jira validate` | Test Jira connection |

Common options:

```bash
mouc gantt --output schedule.md --start-date 2025-01-01
mouc graph --view critical-path --target mobile_launch
mouc doc --format docx --output roadmap.docx
mouc --config mouc_config.yaml gantt
```

## Customization

### Styling

Write Python functions to customize graph colors, shapes, labels, and Gantt task appearance:

```python
# my_styles.py
from mouc.styling import style_node

@style_node
def color_by_status(entity, context):
    if entity.meta.get('status') == 'done':
        return {'fill_color': '#90EE90'}
    return {}
```

```bash
mouc graph --style-file ./my_styles.py
```

Graph nodes can also be boxed into `subgraph cluster_*` groups by any entity field:

```bash
mouc graph --cluster-by meta.repo
```

List values cluster by their first entry, and entities without a value for the field render outside all clusters. For computed cluster keys or custom cluster order, write a `@group_tasks` function instead; such a function overrides the flag, which then has no effect at all.

See [docs/styling.md](docs/styling.md) for the full API.

### Configuration

`mouc_config.yaml` controls resources, scheduling parameters, Jira integration, and output formatting:

```yaml
resources:
  - name: alice
    jira_username: alice@company.com

scheduler:
  algorithm:
    type: parallel_sgs  # or bounded_rollout, cpsat
  strategy: weighted
  cr_weight: 10.0
  priority_weight: 1.0

jira:
  base_url: https://company.atlassian.net

gantt:
  group_by: type
  sort_by: start
```

See [docs/config.md](docs/config.md) for all options.

## Documentation

- [Data Model](docs/data-model.md) - entity types, fields, dependencies
- [Gantt Charts](docs/gantt.md) - scheduling options and output
- [Scheduling Algorithm](docs/scheduling.md) - how the scheduler works
- [Reporting](docs/reporting.md) - effort reports and analysis
- [Workflows](docs/workflows.md) - phase expansion patterns
- [Resources](docs/resources.md) - team definition and auto-assignment
- [Jira Integration](docs/jira.md) - syncing with Jira
- [Styling](docs/styling.md) - customizing output appearance
- [Configuration](docs/config.md) - mouc_config.yaml reference

## Development

```bash
git clone https://github.com/rnortman/mouc.git
cd mouc
uv pip install -e ".[dev]"

# Run tests and checks
pytest
pyright
ruff check src tests
```

## About the Name

Mouc stands for "Mapping Outcomes, User stories, and Capabilities" - reflecting its origin as a dependency tracker for these three entity types. It has since grown into a full scheduling system, but the name stuck.

## License

MIT License - see LICENSE file for details.
