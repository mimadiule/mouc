"""Tests for task organization (grouping and sorting) functionality."""

# pyright: reportUnusedFunction=false, reportPrivateUsage=false

from collections.abc import Sequence
from datetime import date

import pytest

from mouc import builtin_gantt, styling
from mouc.builtin_gantt import register_builtin_organization
from mouc.gantt import GanttScheduler
from mouc.models import Entity, FeatureMap, FeatureMapMetadata
from mouc.styling import Entity as EntityProtocol
from mouc.styling import StylingContext
from mouc.unified_config import GanttConfig
from tests.conftest import deps


def test_group_tasks_decorator_basic() -> None:
    """Test that @group_tasks decorator registers and applies functions."""
    styling.clear_registrations()

    @styling.group_tasks(formats=["gantt"])
    def group_by_team(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        groups: dict[str | None, list[EntityProtocol]] = {}
        for entity in entities:
            team = entity.meta.get("team", "unassigned")
            if team not in groups:
                groups[team] = []
            groups[team].append(entity)
        return groups

    # Create test entities
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Platform Task",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"], "team": "platform"},
        ),
        Entity(
            type="capability",
            id="cap2",
            name="Backend Task",
            description="Test",
            meta={"effort": "5d", "resources": ["bob"], "team": "backend"},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler and generate gantt
    base_date = date(2025, 1, 1)
    scheduler = GanttScheduler(feature_map, start_date=base_date, current_date=base_date)
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Should have custom team sections
    assert "section platform" in mermaid
    assert "section backend" in mermaid
    assert "Platform Task" in mermaid
    assert "Backend Task" in mermaid


def test_group_tasks_priority_override() -> None:
    """Test that higher priority grouping functions override lower priority ones."""
    styling.clear_registrations()

    @styling.group_tasks(priority=5, formats=["gantt"])
    def low_priority_grouping(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        # This should be overridden
        return {"Low Priority": list(entities)}

    @styling.group_tasks(priority=10, formats=["gantt"])
    def high_priority_grouping(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        # This should win
        return {"High Priority": list(entities)}

    # Create test entity
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Test Task",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler and generate gantt
    base_date = date(2025, 1, 1)
    scheduler = GanttScheduler(feature_map, start_date=base_date, current_date=base_date)
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Should use high priority grouping
    assert "section High Priority" in mermaid
    assert "section Low Priority" not in mermaid


def test_group_tasks_dict_order_controls_display() -> None:
    """Test that dict insertion order controls section display order."""
    styling.clear_registrations()

    @styling.group_tasks(formats=["gantt"])
    def ordered_grouping(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        # Explicitly order groups
        ordered = ["Team A", "Team B", "Team C"]
        groups: dict[str | None, list[EntityProtocol]] = {name: [] for name in ordered}

        for entity in entities:
            team = entity.meta.get("team", "Team C")
            if team in groups:
                groups[team].append(entity)

        # Remove empty groups while preserving order
        return {k: v for k, v in groups.items() if v}

    # Create test entities in different order than display order
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Task B",
            description="Test",
            meta={"effort": "5d", "resources": ["bob"], "team": "Team B"},
        ),
        Entity(
            type="capability",
            id="cap2",
            name="Task A",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"], "team": "Team A"},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler and generate gantt
    base_date = date(2025, 1, 1)
    scheduler = GanttScheduler(feature_map, start_date=base_date, current_date=base_date)
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Find section positions
    lines = mermaid.split("\n")
    team_a_idx = next(i for i, line in enumerate(lines) if "section Team A" in line)
    team_b_idx = next(i for i, line in enumerate(lines) if "section Team B" in line)

    # Team A should appear before Team B (dict insertion order)
    assert team_a_idx < team_b_idx


def test_sort_tasks_decorator_basic() -> None:
    """Test that @sort_tasks decorator registers and applies functions."""
    styling.clear_registrations()

    @styling.sort_tasks(formats=["gantt"])
    def sort_by_name(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> list[EntityProtocol]:
        return sorted(entities, key=lambda e: e.name)

    # Create test entities in reverse alphabetical order
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Zebra Task",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
        Entity(
            type="capability",
            id="cap2",
            name="Apple Task",
            description="Test",
            meta={"effort": "5d", "resources": ["bob"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler and generate gantt
    base_date = date(2025, 1, 1)
    scheduler = GanttScheduler(feature_map, start_date=base_date, current_date=base_date)
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Find task positions in output
    lines = mermaid.split("\n")
    apple_idx = next(i for i, line in enumerate(lines) if "Apple Task" in line)
    zebra_idx = next(i for i, line in enumerate(lines) if "Zebra Task" in line)

    # Apple should come before Zebra (alphabetical order)
    assert apple_idx < zebra_idx


def test_sort_tasks_within_groups() -> None:
    """Test that sorting applies within each group."""
    styling.clear_registrations()

    @styling.group_tasks(formats=["gantt"])
    def group_by_team(
        entities: Sequence[EntityProtocol], context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        groups: dict[str | None, list[EntityProtocol]] = {}
        for entity in entities:
            team = entity.meta.get("team", "unassigned")
            if team not in groups:
                groups[team] = []
            groups[team].append(entity)
        return dict(sorted(groups.items()))  # Sort teams alphabetically

    @styling.sort_tasks(formats=["gantt"])
    def sort_by_name(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> list[EntityProtocol]:
        return sorted(entities, key=lambda e: e.name)

    # Create test entities
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Team A - Zebra",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"], "team": "team_a"},
        ),
        Entity(
            type="capability",
            id="cap2",
            name="Team A - Apple",
            description="Test",
            meta={"effort": "5d", "resources": ["bob"], "team": "team_a"},
        ),
        Entity(
            type="capability",
            id="cap3",
            name="Team B - Zebra",
            description="Test",
            meta={"effort": "5d", "resources": ["charlie"], "team": "team_b"},
        ),
        Entity(
            type="capability",
            id="cap4",
            name="Team B - Apple",
            description="Test",
            meta={"effort": "5d", "resources": ["dave"], "team": "team_b"},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler and generate gantt
    base_date = date(2025, 1, 1)
    scheduler = GanttScheduler(feature_map, start_date=base_date, current_date=base_date)
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Each team should be sorted alphabetically within its section
    lines = mermaid.split("\n")

    # Find section boundaries
    team_a_idx = next(i for i, line in enumerate(lines) if "section team_a" in line)
    team_b_idx = next(i for i, line in enumerate(lines) if "section team_b" in line)

    # Find task positions
    team_a_apple_idx = next(i for i, line in enumerate(lines) if "Team A - Apple" in line)
    team_a_zebra_idx = next(i for i, line in enumerate(lines) if "Team A - Zebra" in line)
    team_b_apple_idx = next(i for i, line in enumerate(lines) if "Team B - Apple" in line)
    team_b_zebra_idx = next(i for i, line in enumerate(lines) if "Team B - Zebra" in line)

    # Within Team A: Apple before Zebra
    assert team_a_idx < team_a_apple_idx < team_a_zebra_idx < team_b_idx

    # Within Team B: Apple before Zebra
    assert team_b_idx < team_b_apple_idx < team_b_zebra_idx


def test_config_group_by_type() -> None:
    """Test config-driven grouping by type."""
    styling.clear_registrations()

    # Create test entities of different types
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Infrastructure",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
        Entity(
            type="user_story",
            id="us1",
            name="Login Feature",
            description="Test",
            meta={"effort": "5d", "resources": ["bob"]},
        ),
        Entity(
            type="outcome",
            id="out1",
            name="Q1 Launch",
            description="Test",
            meta={"effort": "1d", "resources": ["charlie"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler with group_by config
    base_date = date(2025, 1, 1)
    gantt_config = GanttConfig(group_by="type")
    scheduler = GanttScheduler(
        feature_map, start_date=base_date, current_date=base_date, gantt_config=gantt_config
    )
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Should have type sections in order
    assert "section Capability" in mermaid
    assert "section User Story" in mermaid
    assert "section Outcome" in mermaid


def test_config_sort_by_start() -> None:
    """Test config-driven sorting by start date."""
    styling.clear_registrations()

    # Create test entities with dependencies (will have different start dates)
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="First Task",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
        Entity(
            type="capability",
            id="cap2",
            name="Second Task",
            description="Test",
            requires=deps("cap1"),
            meta={"effort": "5d", "resources": ["alice"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler with sort_by config
    base_date = date(2025, 1, 1)
    gantt_config = GanttConfig(sort_by="start")
    scheduler = GanttScheduler(
        feature_map, start_date=base_date, current_date=base_date, gantt_config=gantt_config
    )
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Find task positions
    lines = mermaid.split("\n")
    first_idx = next(i for i, line in enumerate(lines) if "First Task" in line)
    second_idx = next(i for i, line in enumerate(lines) if "Second Task" in line)

    # First task should come before second (sorted by start date)
    assert first_idx < second_idx


def test_config_sort_by_name() -> None:
    """Test config-driven sorting by name."""
    styling.clear_registrations()

    # Create test entities in reverse alphabetical order
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Zebra",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
        Entity(
            type="capability",
            id="cap2",
            name="Apple",
            description="Test",
            meta={"effort": "5d", "resources": ["bob"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler with sort_by config
    base_date = date(2025, 1, 1)
    gantt_config = GanttConfig(sort_by="name")
    scheduler = GanttScheduler(
        feature_map, start_date=base_date, current_date=base_date, gantt_config=gantt_config
    )
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Find task positions
    lines = mermaid.split("\n")
    apple_idx = next(i for i, line in enumerate(lines) if "Apple" in line)
    zebra_idx = next(i for i, line in enumerate(lines) if "Zebra" in line)

    # Apple should come before Zebra
    assert apple_idx < zebra_idx


def test_user_function_overrides_config() -> None:
    """Test that user grouping functions override config-driven grouping."""
    styling.clear_registrations()

    @styling.group_tasks(priority=10, formats=["gantt"])
    def custom_grouping(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        return {"Custom Section": list(entities)}

    # Create test entities
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Test",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler with group_by=type config (should be overridden)
    base_date = date(2025, 1, 1)
    gantt_config = GanttConfig(group_by="type")
    scheduler = GanttScheduler(
        feature_map, start_date=base_date, current_date=base_date, gantt_config=gantt_config
    )
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Should use custom grouping, not config grouping
    assert "section Custom Section" in mermaid
    assert "section Capability" not in mermaid


def test_group_tasks_none_key_no_section() -> None:
    """Test that None key in grouping results in no section header."""
    styling.clear_registrations()

    @styling.group_tasks(formats=["gantt"])
    def no_grouping(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        return {None: list(entities)}

    # Create test entity
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Test Task",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler and generate gantt
    base_date = date(2025, 1, 1)
    scheduler = GanttScheduler(feature_map, start_date=base_date, current_date=base_date)
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Should have task but no section header
    assert "Test Task" in mermaid
    assert "section" not in mermaid


def test_multiple_schedulers_dont_conflict() -> None:
    """Test that creating multiple schedulers with different configs doesn't cause conflicts."""
    styling.clear_registrations()

    # Create test entities
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Test",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)
    base_date = date(2025, 1, 1)

    # Create scheduler with type grouping
    config1 = GanttConfig(group_by="type")
    scheduler1 = GanttScheduler(
        feature_map, start_date=base_date, current_date=base_date, gantt_config=config1
    )
    result1 = scheduler1.schedule()
    mermaid1 = scheduler1.generate_mermaid(result1)

    # Create scheduler with resource grouping
    config2 = GanttConfig(group_by="resource")
    scheduler2 = GanttScheduler(
        feature_map, start_date=base_date, current_date=base_date, gantt_config=config2
    )
    result2 = scheduler2.schedule()
    mermaid2 = scheduler2.generate_mermaid(result2)

    # Each should have its own grouping
    assert "section Capability" in mermaid1
    assert "section alice" not in mermaid1

    assert "section alice" in mermaid2
    assert "section Capability" not in mermaid2


def test_format_filtering_for_organization() -> None:
    """Test that format filtering works for group_tasks and sort_tasks."""
    styling.clear_registrations()

    @styling.group_tasks(formats=["other_format"])
    def wrong_format_grouping(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        return {"Wrong Format": list(entities)}

    @styling.group_tasks(formats=["gantt"])
    def correct_format_grouping(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        return {"Correct Format": list(entities)}

    # Create test entity
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Test",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler
    base_date = date(2025, 1, 1)
    scheduler = GanttScheduler(feature_map, start_date=base_date, current_date=base_date)
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Should use gantt-format grouping only
    assert "section Correct Format" in mermaid
    assert "section Wrong Format" not in mermaid


def test_clear_registrations_clears_organization_functions() -> None:
    """Test that clear_registrations clears group_tasks and sort_tasks."""
    styling.clear_registrations()

    @styling.group_tasks(formats=["gantt"])
    def my_grouping(
        entities: Sequence[EntityProtocol], _context: StylingContext
    ) -> dict[str | None, list[EntityProtocol]]:
        return {"My Group": list(entities)}

    # Clear and verify it's gone
    styling.clear_registrations()

    # Create test entity
    entities = [
        Entity(
            type="capability",
            id="cap1",
            name="Test",
            description="Test",
            meta={"effort": "5d", "resources": ["alice"]},
        ),
    ]
    feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    # Create scheduler without config
    base_date = date(2025, 1, 1)
    scheduler = GanttScheduler(feature_map, start_date=base_date, current_date=base_date)
    result = scheduler.schedule()
    mermaid = scheduler.generate_mermaid(result)

    # Should have no grouping (default behavior)
    assert "section" not in mermaid


class TestBuiltinOrganizationLookupTables:
    """Test that every config value binds to the intended built-in function."""

    @pytest.mark.parametrize(
        ("group_by", "expected"),
        [
            ("type", builtin_gantt._builtin_group_by_type),
            ("resource", builtin_gantt._builtin_group_by_resource),
            ("timeframe", builtin_gantt._builtin_group_by_timeframe),
        ],
    )
    def test_group_by_registers_expected_func(
        self, group_by: str, expected: styling.GroupTasksFunc
    ) -> None:
        register_builtin_organization(group_by, None)

        assert [reg.func for reg in styling._group_tasks_funcs] == [expected]
        assert styling._sort_tasks_funcs == []

    @pytest.mark.parametrize(
        ("sort_by", "expected"),
        [
            ("start", builtin_gantt._builtin_sort_by_start),
            ("end", builtin_gantt._builtin_sort_by_end),
            ("deadline", builtin_gantt._builtin_sort_by_deadline),
            ("name", builtin_gantt._builtin_sort_by_name),
            ("priority", builtin_gantt._builtin_sort_by_priority),
        ],
    )
    def test_sort_by_registers_expected_func(
        self, sort_by: str, expected: styling.SortTasksFunc
    ) -> None:
        register_builtin_organization(None, sort_by)

        assert [reg.func for reg in styling._sort_tasks_funcs] == [expected]
        assert styling._group_tasks_funcs == []

    @pytest.mark.parametrize("value", [None, "none", "yaml_order", "bogus"])
    def test_unrecognized_values_register_nothing(self, value: str | None) -> None:
        register_builtin_organization(value, value)

        assert styling._group_tasks_funcs == []
        assert styling._sort_tasks_funcs == []
