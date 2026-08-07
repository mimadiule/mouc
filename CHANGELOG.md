# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-08-07

### Added
- `mouc graph --cluster-by <field.path>` groups nodes into subgraph clusters.

### Changed
- `@group_tasks` functions now also define graph clusters; scope with `formats=['gantt']` to opt out.

### Fixed
- Graph labels containing backslashes no longer produce invalid DOT output.

## [0.7.6] - 2026-05-06

### Fixed
- `mouc graph --tags` now actually filters output (previously ignored).

### Changed
- `--tags` filter behavior unified across `graph`, `doc`, `gantt`, `schedule`: shared grammar with include/exclude (`!tag`) and configurable closure direction (`--tags-direction up|down|both`).

## [0.7.5] - 2026-01-29

### Fixed
- Rollout analysis no longer considers the current task as a competitor with itself

## [0.7.4] - 2026-01-08

### Added
- Phase `requires` override: workflow phases can specify additional dependencies via `phases.<phase>.requires`
- Graph-aware workflows: `WorkflowContext` provides access to full entity graph for intelligent dependency wiring
- Two-pass workflow expansion with `PhaseDiscovery` for pre-computing phase IDs and state
- Declarative `phases` config for custom workflows: specify phase ID templates instead of implementing `discover_phases()`

### Changed
- `mouc convert-format` now preserves YAML block scalars and list formatting
- Require manylinux_2_28 (glibc 2.28+) for Linux wheels

## [0.7.3] - 2025-12-19

### Changed
- Lock file format updated to version 2 with `was_fixed` and `resources_were_computed` fields

## [0.7.2] - 2025-12-19

### Added
- `mouc doc --lock-file` option to use pre-computed schedule from lock file
- `mouc report effort` command: Generate CSV reports of task effort within a time range

### Fixed
- Config auto-discovery now checks the feature map directory before falling back to current directory
- Effort parsing: `5d` now correctly means 5 work days (= 7 calendar days), not 5 calendar days

## [0.7.1] - 2025-12-18

- Fix CI packaging

## [0.7.0] - 2025-12-18

### Changed
- Critical path urgency can now exceed 1.0 for slipping deadlines (negative slack)
- Removed `default_priority` from `critical_path` config section; now uses global `scheduler.default_priority`
- CP-SAT scheduler now rejects multi-resource tasks (use `resource_spec` for auto-assignment instead)
- CP-SAT scheduler now supports DNS splitting (tasks can span DNS periods, matching greedy scheduler behavior)
- Scheduler performance: caching, binary search, and reduced logging in hot paths
- Bounded rollout: memoize `calculate_completion_time`, configurable `max_horizon_days` (default 30)

### Fixed
- `next_available_time` now correctly handles consecutive/overlapping busy periods
- Bounded rollout scheduler uses configured strategy for urgent task sorting
- Bounded rollout scheduler uses rollout for resource choice when best resource unavailable

### Added
- CSV output filtering: `@filter_entity(formats=['csv'])` filters apply to `--output-csv` output
- Phased scheduling: `schedule --output-lock`, `--lock-file`, `--style-tags`, `--style-file` for multi-pass scheduling
- `gantt --lock-file` to render charts from pre-computed schedules (skips scheduling)
- `schedule --output-csv` and `compare` commands for scenario analysis
- Critical path scheduler (`--algorithm critical_path --rust`) - eliminates priority contamination by focusing on critical path tasks
- Critical path rollout: simulates resource assignment decisions to avoid blocking higher-priority work
- A reimplementation of the greedy schedulers in Rust for performance
- `--rust` CLI flag for `gantt` and `schedule` commands to use Rust scheduler implementation
- `scheduler.implementation` config option (`python` or `rust`) to select scheduler implementation
- `scheduler.algorithm.type: cpsat` - OR-Tools CP-SAT optimal scheduler
- `scheduler.preprocessor.type: auto` - Default preprocessor skips backward pass for CP-SAT (global optimizer doesn't need it)
- `scheduler.auto_constraint_from_timeframe` config: control whether timeframe creates scheduling constraints (`both`, `start`, `end`, `none`)
- `scheduler.strategy: atc` - Apparent Tardiness Cost scheduling strategy with exponential deadline urgency
- `scheduler.cpsat.use_greedy_hints` - Run greedy scheduler first to seed CP-SAT with hints and tighter horizon (default: true)
- `scheduler.cpsat.warn_on_incomplete_hints` - Warn if greedy hints are incomplete or rejected (default: true)
- `scheduler.cpsat.log_solver_progress` - Log CP-SAT solver progress at verbosity level 1 (default: false)

## [0.6.4] - 2025-12-11

### Fixed
- Jira sync now preserves existing phase meta fields when syncing new fields

## [0.6.3] - 2025-12-10

### Fixed
- Filtered entity references now render as plain text instead of broken links

## [0.6.2] - 2025-12-10

### Fixed
- Entity filter functions no longer create broken links in document/graph output
- References to filtered entities marked as "(filtered)" or omitted via `filtered_reference_handling` config
- Graph edges to filtered entities are now omitted

## [0.6.1] - 2025-12-10

### Fixed
- Deadline propagation now uses dependent task's duration (not dependency's)

## [0.6.0] - 2025-12-10

### Added
- Negated style tags: `tags=["!detailed"]` runs only when tag is NOT active
- User-configurable entity types via `entity_types` config section
- `mouc convert-format` command for migrating to unified `entities` format
- Dependency lag: `requires: [task_a + 1w]` delays start after dependency completes
- Workflows: expand entities into phases via `workflow: design_impl` field
- Type-based default workflows: `workflows.defaults.capability: design_impl`
- `workflow: none` to override default and prevent expansion
- `save_resolution_choices` config for Jira sync conflict resolution persistence
- `transition_to_status` accepts list of statuses, uses earliest matching date

### Changed
- Entity types validated against configured types (supports custom types)
- Old 3-section YAML format emits deprecation warning
- Graph nodes default to white fill; use styling functions for type colors
- Backward dependency warnings use scheduler data for entities without manual timeframes

## [0.5.1] - 2025-12-09

### Added
- Configurable `default_priority`, `default_cr_multiplier`, and `default_cr_floor` in scheduler config

### Changed
- **Breaking**: Unified default CR calculation for tasks without deadlines uses `max(max_cr * multiplier, floor)` formula
- **Breaking**: Removed `default_cr` config option (replaced by `default_cr_multiplier` and `default_cr_floor`)

## [0.5.0] - 2025-12-08

### Added
- Bounded rollout scheduling algorithm with CR-aware triggering

### Changed
- Refactored scheduler into pluggable architecture
- Added `--algorithm` CLI flag to `schedule` and `gantt` commands

## [0.4.5] - 2025-12-08

### Added
- Tag-based styler filtering: `--style-tags` CLI option and `style_tags` config to selectively enable styler functions

## [0.4.4] - 2025-12-02

### Changed
- Zero-duration tasks are now milestones: no resource assignment, render with `:milestone` tag in Gantt charts

## [0.4.3] - 2025-12-02

### Fixed
- Zero-duration tasks no longer get artificially deprioritized in CR scheduling

## [0.4.2] - 2025-11-21

### Fixed
- Fixed doc output to respect DNS periods for tasks with fixed start_date but no end_date

## [0.4.1] - 2025-11-20

### Fixed
- Resource exclusion syntax now works in gantt charts (consolidated duplicate resource parsing logic)
- Group expansion with exclusions now works correctly in resource specs

## [0.4.0] - 2025-11-20

### Added
- Resource exclusion syntax: Use `!resource` to exclude specific resources (e.g., `*|!bob`, `team_a|!alice`)

## [0.3.0] - 2025-11-19

### Added
- Entity filtering: `@filter_entity` decorator works across all outputs (doc, graph, gantt)
- Gantt organization system: `@group_tasks` and `@sort_tasks` decorators for custom task organization
- Config-driven gantt grouping: `gantt.group_by` (none, type, resource, timeframe)
- Config-driven gantt sorting: `gantt.sort_by` (yaml_order, start, end, deadline, name, priority)
- CLI `--group-by` and `--sort-by` options for gantt charts

### Changed
- Default gantt grouping changed from `type` to `none` (no sections)

## [0.2.0] - 2025-11-18

### Added
- Global DNS periods: Company-wide DNS periods that apply to all resources (e.g., holidays, offsites)
- Format-specific styling: Decorators support `formats` parameter to filter by output format
- Gantt charts now display date axis at top via `topAxis: true`
- Markdown formatting in entity descriptions: Bold, italic, links, inline code, lists, and code blocks now supported in both markdown and DOCX output
- Timeline grouping: Infer timeframe from scheduler completion dates with configurable granularity (weekly, monthly, quarterly, half_year, yearly)
- Timeline sorting: Sort unscheduled section by completion date instead of entity type/ID
- Body organization: Use inferred timeframes in document body (not just ToC)
- Confirmed/inferred separation: Separate manual timeframes from auto-scheduled timeframes in output

### Changed
- "Requires" and "Enables" sections: markdown uses headings (h4/h5), DOCX uses bold text
- CLI exception handling removed to show full backtraces
- Entity ID, tags, and links now included in metadata, styleable via `@style_metadata` decorators

### Fixed
- Fixed task end dates now account for DNS periods when only start_date is specified
- Format filtering for `@style_metadata` decorators now works correctly

## [0.1.12] - 2025-11-13

### Fixed
- Missing source file from 0.1.11

## [0.1.11] - 2025-11-12

### Fixed
- DNS period handling edge case

### Added
- **Scheduling debug mode**: Use `-v 1/2/3` to view scheduling decisions at different detail levels
- **Verbose logging overhaul**: Improved logging structure and consistency

## [0.1.10] - 2025-11-11

### Added
- **Critical Ratio scheduling**: Scheduler now prioritizes tasks by CR (slack/duration) instead of raw deadlines, correctly accounting for task duration
- **Priority metadata field**: New `priority` field (0-100, default 50) controls task urgency independent of deadlines
- **Scheduling strategies**: Configurable via `SchedulingConfig` (programmatic only for now)
  - `priority_first`: Sort by priority, then CR (lexicographic)
  - `cr_first`: Sort by CR, then priority (lexicographic)
  - `weighted`: Composite score with tunable weights (default: CR-heavy with 10:1 ratio)
- **Adaptive median CR**: Tasks without deadlines automatically get median CR of deadline tasks, updated dynamically as work progresses
- **DNS-aware scheduling with completion-time foresight**: Scheduler now makes intelligent resource assignments accounting for DNS interruptions
  - Tasks can start before DNS and resume after if this completes sooner than waiting
  - Auto-assigned tasks compare completion times across resources and pick the fastest
  - High-urgency tasks wait for optimal resources while lower-urgency tasks backfill
- **DOCX output format**: `mouc doc --format docx` generates Microsoft Word documents
- **Markdown document organization**: New `markdown.organization` config controls entity grouping and sorting
  - Primary grouping: `by_type`, `by_timeframe`, `alpha_by_id`, or `yaml_order`
  - Secondary grouping: nest timeframes within types or types within timeframes
  - Configurable entity type order when using `by_type`
- **ToC suppression**: Set `markdown.toc_sections: []` to suppress table of contents

### Changed
- **Breaking**: `toc_sections` values changed from `["timeline", "capabilities", "user_stories", "outcomes"]` to `["timeline", "entity_types"]`
- **Breaking**: `markdown.sections` renamed to `markdown.toc_sections` for clarity
- **Breaking**: Refactored markdown generation to use pluggable backend architecture for future format support (docx, html)
- **Breaking**: Scheduler now uses CR-based prioritization; tasks with same deadline but different durations schedule differently

## [0.1.9] - 2025-11-09

### Fixed
- **Scheduler deadline propagation**: Fixed bug preventing deadlines from propagating through long dependency chains

### Added
- **Markdown output configuration**: New `markdown.sections` config controls which sections appear and in what order
- **Schedule annotations**: New `mouc schedule` command runs scheduling and outputs/persists results
- **Scheduling in doc command**: `mouc doc --schedule` computes annotations before rendering markdown
  - Enables styling functions to access and display computed scheduling information
  - Example styling file: `examples/schedule_markdown_style.py`
- **Gantt chart task styling**: Custom CSS colors for tasks via `@style_task` decorator (fill_color, stroke_color, text_color)
- **Gantt chart clickable links**: Tasks in gantt charts can now link to markdown documentation
- **Jira sync metadata**: New `jira_sync` metadata field controls sync behavior per entity
  - `ignore_fields`: Block specific fields from Jira sync entirely
  - `ignore_values`: Skip specific bad values from Jira history
  - `resolution_choices`: Remember user's conflict resolution decisions for future syncs
  - Validation layer detects invalid data (e.g., start_date > end_date) and creates conflicts
  - CLI commands: `jira ignore-field`, `jira ignore-value`, `jira show-overrides`
- **Unified configuration file**: New `mouc_config.yaml` format consolidates resources and Jira settings
- **`.netrc` credential support for Jira**: Jira credentials can now be retrieved from `~/.netrc` as an alternative to environment variables
- **Verbosity for Jira commands**: Global `-v/--verbose` flag with levels 0-3
  - **`jira sync`**:
    - Level 0 (default): Silent, only show summary
    - Level 1: Show field changes with "old → new" format
    - Level 2: Show all entities being checked, even without changes
    - Level 3: Debug mode with detailed Jira field extraction logging
    - `--dry-run` automatically enables verbosity level 1 if not already set
  - **`jira fetch`**:
    - Level 0 (default): Basic issue info and status transitions
    - Level 1: Enhanced display with status transition history
    - Level 2: Show all Jira fields from the issue
    - Level 3: Dump complete raw Jira API response (issue + changelog + field definitions)

### Changed
- **Breaking**: `mouc graph -v` short flag removed; use `--view` instead to avoid conflict with global verbosity flag
- **Breaking**: Separate `resources.yaml` and `jira_config.yaml` files no longer supported; must use unified `mouc_config.yaml`

## [0.1.8] - 2025-11-06

### Fixed
- **Scheduler now resumes work after DNS periods end**: Fixed a critical bug where the scheduler would fail to schedule tasks after resource DNS (Do Not Schedule) periods ended, leaving large gaps in the schedule even when resources were available. The scheduler now properly considers DNS period end dates when advancing time.

## [0.1.7] - 2025-11-06

### Added
- **Task completion tracking**: New `status: done` metadata field marks tasks as completed
  - Tasks with `status: done` and dates render with `:done` tag (gray) in Gantt charts
  - Tasks with `status: done` but no dates are excluded from Gantt output but satisfy dependencies
  - Warning generated for done tasks without dates: "Task '{id}' marked done without dates - excluded from schedule"
  - Done tasks without dates allow dependent tasks to start immediately
- **Alpha-quality Jira integration**: Adds the ability to query Jira for entities with `jira` links and sync start/end dates, status, and assignee. See [docs/jira.md](docs/jira.md) for information. This feature is very rough and is likely to change substantially in the future.

### Fixed
- Manual scheduling now correctly overrides DNS periods: tasks with explicit `start_date` or `end_date` are always scheduled at those times, even if the assigned resource has a DNS (Do Not Schedule) period during that time

## [0.1.6] - 2025-11-05

### Added
- **Automatic resource assignment**: Scheduler can now automatically assign tasks to resources
  - Resource configuration file (`resources.yaml`) defines available resources, DNS periods, and groups
  - Wildcard assignment: `resources: ["*"]` assigns to first available resource
  - Preference lists: `resources: ["alice|bob|charlie"]` tries resources in order
  - Resource groups: define aliases like `team_a: [alice, bob]` for convenient assignment
  - DNS (Do Not Schedule) periods block resource assignment during specified time ranges
  - `default_resource` configuration option for tasks with no explicit assignment
  - CLI option `--resources resources.yaml` to enable automatic assignment
  - Dynamic assignment respects deadline priorities (high-priority tasks get first pick)
- Gantt chart customization options for Mermaid output
  - `--tick-interval` option to control x-axis tick spacing (e.g., `1week`, `1month`, `3month`)
  - `--axis-format` option to customize date display format (e.g., `%Y-%m-%d`, `%b %Y`)
  - `--vertical-dividers` option to add visual markers for quarters, half-years, or years
  - `--compact` option

## [0.1.5] - 2025-11-04

### Added
- **Gantt chart scheduling**: New `mouc gantt` command generates resource-aware Gantt charts in Mermaid format
  - Resource-constrained project scheduling with deadline tracking and propagation
  - Support for effort estimates (`1d`, `2w`, `1.5m`, `L`) and resource allocations (`alice:0.5`)
  - Flexible timeframe parsing: quarters (`2025q1`), weeks (`2025w01`), months (`2025-01`)
  - Resource grouping option: `--group-by resource` to organize by person/team
  - Fixed-date tasks with `start_date`/`end_date` metadata
  - Visual indicators for deadline violations and unassigned tasks
  - Dual date system: `--start-date` for chart start, `--current-date` for scheduling baseline

## [0.1.4] - 2025-09-30

### Added
- Bidirectional edge specification: can now use `requires` and `enables` fields to specify dependencies from either direction
- **Styling system**: Flexible styling system for customizing graph and markdown output
  - User-defined styling functions via Python decorators (`@style_node`, `@style_edge`, `@style_label`)
  - Protocol-based API compatible with mypy/pyright
  - Priority-based composition of multiple style functions
  - Graph analysis context with transitive dependency queries
  - Utility functions for sequential color generation and contrast calculation
  - CLI options `--style-module` and `--style-file` for loading styling functions

### Changed
- Renamed `dependencies` field to `requires` (old field still works with deprecation warning)
- Markdown section headers changed from "Dependencies" to "Requires" and "Required by" to "Enables"
- Graph output now includes default styling that can be overridden by user styling functions

### Deprecated
- `dependencies` field is deprecated in favor of `requires` (backward compatible with warning to stderr)

## [0.1.3] - 2025-09-30

### Changed
- Updated graph coloring for better visibility

## [0.1.2] - 2025-09-30

### Added
- New `timeframe-colored` graph view that uses sequential colors to represent timeframes

## [0.1.1] - 2025-09-30

### Fixed
- Fixed backward-in-time dependency check to correctly flag scheduled entities depending on unscheduled entities as backward dependencies

## [0.1.0] - 2025-09-30

### Added
- Initial release
- YAML-based feature map tracking capabilities, user stories, and outcomes
- Entity dependency tracking and validation
- Markdown documentation generator with timeline view
- Graph visualization using Graphviz
- Backward dependency detection for timeline-scheduled entities
- CLI interface with commands for validation, markdown generation, and graph visualization
- Support for custom metadata fields on entities
- Link tracking (Jira, design docs, etc.)
