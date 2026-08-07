"""Tests for graph clustering: the --cluster-by built-in and @group_tasks integration."""

# pyright: reportPrivateUsage=false, reportUnusedFunction=false

from collections.abc import Sequence
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mouc import styling
from mouc.builtin_gantt import register_builtin_organization
from mouc.builtin_graph import (
    register_builtin_clustering,
    resolve_cluster_value,
    validate_cluster_path,
)
from mouc.cli import app
from mouc.graph import GraphGenerator, GraphView
from mouc.models import Entity, FeatureMap, FeatureMapMetadata
from mouc.parser import resolve_graph_edges
from mouc.styling import BUILTIN_PRIORITY, StylingContext
from mouc.styling import Entity as EntityProtocol
from tests.conftest import deps

runner = CliRunner()


def _entity(entity_id: str = "e1", **kwargs: object) -> Entity:
    """Build a minimal entity with the given field overrides."""
    fields: dict[str, object] = {
        "type": "capability",
        "id": entity_id,
        "name": entity_id,
        "description": "desc",
    }
    fields.update(kwargs)
    return Entity(**fields)  # pyright: ignore[reportArgumentType]


def _parse_clusters(dot: str) -> tuple[dict[str, list[str]], list[str]]:
    """Split DOT output into cluster label -> node IDs, plus top-level node IDs."""
    clusters: dict[str, list[str]] = {}
    top_level: list[str] = []
    current: list[str] | None = None

    for line in dot.splitlines():
        stripped = line.strip()
        if stripped.startswith("subgraph cluster_"):
            current = []
        elif current is not None and stripped.startswith('label="'):
            clusters[stripped[len('label="') : -2]] = current
        elif stripped == "}":
            current = None
        elif "[label=" in stripped:
            node_id = stripped.split(" ", 1)[0]
            if current is None:
                top_level.append(node_id)
            else:
                current.append(node_id)

    return clusters, top_level


class TestValidateClusterPath:
    """Test field path validation."""

    def test_single_segment(self) -> None:
        assert validate_cluster_path("meta") == ["meta"]

    def test_multiple_segments(self) -> None:
        assert validate_cluster_path("meta.team.name") == ["meta", "team", "name"]

    def test_unknown_first_segment(self) -> None:
        with pytest.raises(ValueError, match="'mata' is not an entity field"):
            validate_cluster_path("mata.repo")

    @pytest.mark.parametrize("path", ["", ".", "meta.", ".repo", "meta..repo"])
    def test_empty_segment(self, path: str) -> None:
        with pytest.raises(ValueError, match="empty path segment"):
            validate_cluster_path(path)


class TestResolveClusterValue:
    """Test resolution of a validated field path to a cluster key."""

    def test_string_value(self) -> None:
        entity = _entity(meta={"repo": "alpha"})
        assert resolve_cluster_value(entity, ["meta", "repo"]) == "alpha"

    def test_list_takes_first_entry(self) -> None:
        entity = _entity(meta={"repo": ["beta", "alpha"]})
        assert resolve_cluster_value(entity, ["meta", "repo"]) == "beta"

    def test_empty_list_is_unclustered(self) -> None:
        entity = _entity(meta={"repo": []})
        assert resolve_cluster_value(entity, ["meta", "repo"]) is None

    def test_list_of_none_is_unclustered(self) -> None:
        entity = _entity(meta={"repo": [None]})
        assert resolve_cluster_value(entity, ["meta", "repo"]) is None

    def test_missing_key_is_unclustered(self) -> None:
        entity = _entity(meta={"other": "alpha"})
        assert resolve_cluster_value(entity, ["meta", "repo"]) is None

    def test_explicit_none_is_unclustered(self) -> None:
        entity = _entity(meta={"repo": None})
        assert resolve_cluster_value(entity, ["meta", "repo"]) is None

    def test_nested_path(self) -> None:
        entity = _entity(meta={"team": {"name": "platform"}})
        assert resolve_cluster_value(entity, ["meta", "team", "name"]) == "platform"

    def test_non_dict_mid_path_is_unclustered(self) -> None:
        entity = _entity(meta={"repo": "alpha"})
        assert resolve_cluster_value(entity, ["meta", "repo", "name"]) is None

    def test_top_level_field(self) -> None:
        entity = _entity(type="outcome")
        assert resolve_cluster_value(entity, ["type"]) == "outcome"

    def test_int_value_becomes_string(self) -> None:
        entity = _entity(meta={"wave": 1})
        assert resolve_cluster_value(entity, ["meta", "wave"]) == "1"

    def test_bool_value_becomes_string(self) -> None:
        entity = _entity(meta={"internal": True})
        assert resolve_cluster_value(entity, ["meta", "internal"]) == "True"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("", ""), (0, "0"), (False, "False"), (1.5, "1.5")],
    )
    def test_falsy_and_float_scalars_are_keys(self, value: object, expected: str) -> None:
        """Every scalar keys a cluster; falsiness is not emptiness."""
        entity = _entity(meta={"repo": value})
        assert resolve_cluster_value(entity, ["meta", "repo"]) == expected

    def test_dict_final_value_raises(self) -> None:
        entity = _entity("cap1", meta={"repo": "alpha"})
        with pytest.raises(ValueError, match="Entity 'cap1'.*'meta' resolves to a dict"):
            resolve_cluster_value(entity, ["meta"])

    def test_set_field_raises(self) -> None:
        entity = _entity("cap1", requires=deps("cap0"))
        with pytest.raises(ValueError, match="Entity 'cap1'.*'requires' resolves to a set"):
            resolve_cluster_value(entity, ["requires"])

    def test_tuple_field_raises(self) -> None:
        entity = _entity("cap1", phase_of=("parent", "design"))
        with pytest.raises(ValueError, match="Entity 'cap1'.*'phase_of' resolves to a tuple"):
            resolve_cluster_value(entity, ["phase_of"])

    def test_nested_list_raises(self) -> None:
        entity = _entity("cap1", meta={"repo": [["alpha"]]})
        with pytest.raises(ValueError, match="resolves to a list"):
            resolve_cluster_value(entity, ["meta", "repo"])

    def test_unset_optional_field_is_unclustered(self) -> None:
        entity = _entity()
        assert resolve_cluster_value(entity, ["phase_of"]) is None


class TestRegisterBuiltinClustering:
    """Test registration lifecycle of the --cluster-by built-in."""

    def test_registers_at_builtin_priority_for_graph(self) -> None:
        register_builtin_clustering("meta.repo")

        assert len(styling._group_tasks_funcs) == 1
        reg = styling._group_tasks_funcs[0]
        assert reg.priority == BUILTIN_PRIORITY
        assert reg.formats == ["graph"]
        assert reg.tags is None

    def test_repeated_registration_replaces(self) -> None:
        register_builtin_clustering("meta.repo")
        register_builtin_clustering("meta.team")

        assert len(styling._group_tasks_funcs) == 1

    def test_none_clears_registration(self) -> None:
        register_builtin_clustering("meta.repo")
        register_builtin_clustering(None)

        assert styling._group_tasks_funcs == []

    def test_returns_registered_func_and_segments(self) -> None:
        clustering = register_builtin_clustering("meta.repo")

        assert clustering is not None
        assert clustering.segments == ["meta", "repo"]
        assert clustering.func is styling._group_tasks_funcs[0].func

    def test_returns_none_when_nothing_registered(self) -> None:
        assert register_builtin_clustering(None) is None

    def test_invalid_path_raises_without_registering(self) -> None:
        with pytest.raises(ValueError, match="not an entity field"):
            register_builtin_clustering("bogus.repo")

        assert styling._group_tasks_funcs == []

    def test_does_not_clobber_gantt_builtin(self) -> None:
        register_builtin_organization("type", None)
        register_builtin_clustering("meta.repo")

        formats = [reg.formats for reg in styling._group_tasks_funcs]
        assert formats == [["gantt"], ["graph"]]

    def test_gantt_builtin_does_not_clobber_clustering(self) -> None:
        register_builtin_clustering("meta.repo")
        register_builtin_organization("type", None)

        formats = [reg.formats for reg in styling._group_tasks_funcs]
        assert formats == [["graph"], ["gantt"]]


class TestClusteredRendering:
    """Test DOT rendering with a grouping function registered."""

    @pytest.fixture
    def clustered_feature_map(self) -> FeatureMap:
        """Feature map with repo metadata, one entity lacking it, and timeframes."""
        cap1 = _entity("cap1", meta={"repo": "alpha", "timeframe": "Q1 2025"}, tags=["infra"])
        cap2 = _entity(
            "cap2",
            meta={"repo": ["beta", "alpha"], "timeframe": "Q1 2025"},
            requires=deps("cap1"),
            tags=["infra"],
        )
        cap3 = _entity(
            "cap3", meta={"repo": "alpha", "timeframe": "Q2 2025"}, requires=deps("cap2")
        )
        story1 = _entity("story1", type="user_story", meta={}, requires=deps("cap2"))
        outcome1 = _entity(
            "outcome1",
            type="outcome",
            meta={"repo": "beta", "timeframe": "Q3 2025"},
            requires=deps("cap3", "story1"),
        )

        entities = [cap1, cap2, cap3, story1, outcome1]
        resolve_graph_edges(entities)
        return FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    def test_all_view_clusters_by_repo(self, clustered_feature_map: FeatureMap) -> None:
        register_builtin_clustering("meta.repo")
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.ALL)

        clusters, top_level = _parse_clusters(dot)
        assert clusters == {"alpha": ["cap1", "cap3"], "beta": ["cap2", "outcome1"]}
        assert top_level == ["story1"]

    def test_cluster_labels_sorted(self, clustered_feature_map: FeatureMap) -> None:
        register_builtin_clustering("meta.repo")
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.ALL)

        clusters, _ = _parse_clusters(dot)
        assert list(clusters) == ["alpha", "beta"]
        assert "subgraph cluster_0" in dot
        assert "subgraph cluster_1" in dot

    def test_cluster_box_style(self, clustered_feature_map: FeatureMap) -> None:
        register_builtin_clustering("meta.repo")
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.ALL)

        assert (
            '  subgraph cluster_0 {\n    label="alpha";\n'
            "    style=filled;\n    fillcolor=lightgrey;\n"
        ) in dot

    def test_edges_preserved(self, clustered_feature_map: FeatureMap) -> None:
        register_builtin_clustering("meta.repo")
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.ALL)

        assert "cap1 -> cap2;" in dot
        assert "cap2 -> cap3;" in dot
        assert "cap2 -> story1;" in dot
        assert "story1 -> outcome1;" in dot

    def test_no_registration_leaves_graph_flat(self, clustered_feature_map: FeatureMap) -> None:
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.ALL)

        assert "subgraph cluster_" not in dot
        clusters, top_level = _parse_clusters(dot)
        assert clusters == {}
        assert top_level == ["cap1", "cap2", "cap3", "story1", "outcome1"]

    def test_label_escaping(self) -> None:
        entity = _entity("cap1", meta={"repo": 'a "quoted" repo'})
        feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=[entity])
        register_builtin_clustering("meta.repo")

        dot = GraphGenerator(feature_map).generate(GraphView.ALL)

        assert 'label="a \\"quoted\\" repo";' in dot

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("C:\\repos\\x", 'label="C:\\\\repos\\\\x";'),
            ("trailing\\", 'label="trailing\\\\";'),
            ('esc\\"', 'label="esc\\\\\\"";'),
        ],
    )
    def test_backslash_labels_stay_quoted(self, value: str, expected: str) -> None:
        """Backslashes are escaped so a value cannot terminate or extend the DOT string."""
        entity = _entity("cap1", meta={"repo": value})
        feature_map = FeatureMap(metadata=FeatureMapMetadata(), entities=[entity])
        register_builtin_clustering("meta.repo")

        dot = GraphGenerator(feature_map).generate(GraphView.ALL)

        assert expected in dot

    def test_critical_path_node_order_is_declaration_order(
        self, clustered_feature_map: FeatureMap
    ) -> None:
        """Nothing registered: nodes follow entity declaration order, not set iteration order."""
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.CRITICAL_PATH, target="cap3")

        _, top_level = _parse_clusters(dot)
        assert top_level == ["cap1", "cap2", "cap3"]

    def test_filtered_node_order_is_declaration_order(
        self, clustered_feature_map: FeatureMap
    ) -> None:
        """Nothing registered: nodes follow entity declaration order, not set iteration order."""
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.FILTERED, tags=["infra"])

        _, top_level = _parse_clusters(dot)
        assert top_level == ["cap1", "cap2", "cap3", "story1"]

    def test_critical_path_view_clusters(self, clustered_feature_map: FeatureMap) -> None:
        register_builtin_clustering("meta.repo")
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.CRITICAL_PATH, target="cap3")

        clusters, top_level = _parse_clusters(dot)
        assert clusters == {"alpha": ["cap1", "cap3"], "beta": ["cap2"]}
        assert top_level == []
        assert "cap1 -> cap2;" in dot

    def test_filtered_view_clusters(self, clustered_feature_map: FeatureMap) -> None:
        register_builtin_clustering("meta.repo")
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.FILTERED, tags=["infra"])

        clusters, top_level = _parse_clusters(dot)
        assert clusters == {"alpha": ["cap1", "cap3"], "beta": ["cap2"]}
        assert top_level == ["story1"]

    def test_timeframe_colored_view_keeps_colors_in_clusters(
        self, clustered_feature_map: FeatureMap
    ) -> None:
        register_builtin_clustering("meta.repo")
        dot = GraphGenerator(clustered_feature_map).generate(GraphView.TIMEFRAME_COLORED)

        clusters, top_level = _parse_clusters(dot)
        assert clusters == {"alpha": ["cap1", "cap3"], "beta": ["cap2", "outcome1"]}
        assert top_level == ["story1"]
        # story1 has no timeframe; clustered nodes keep their timeframe hue
        assert 'story1 [label="story1", shape=oval, style=filled, fillcolor="lightgray"];' in dot
        assert 'fillcolor="lightgray"' in dot
        assert dot.count('fillcolor="white"') == 0

    def test_timeline_view_ignores_grouping(self, clustered_feature_map: FeatureMap) -> None:
        generator = GraphGenerator(clustered_feature_map)
        without_grouping = generator.generate(GraphView.TIMELINE)

        register_builtin_clustering("meta.repo")
        assert generator.generate(GraphView.TIMELINE) == without_grouping

    def test_non_scalar_value_raises_during_generation(
        self, clustered_feature_map: FeatureMap
    ) -> None:
        register_builtin_clustering("meta")

        with pytest.raises(ValueError, match="cannot be used as a cluster key"):
            GraphGenerator(clustered_feature_map).generate(GraphView.ALL)


class TestUserGroupingFunctions:
    """Test @group_tasks interaction with graph clustering."""

    @pytest.fixture
    def feature_map(self) -> FeatureMap:
        """Two-entity feature map with one dependency edge."""
        cap1 = _entity("cap1", meta={"repo": "alpha"})
        cap2 = _entity("cap2", meta={"repo": "beta"}, requires=deps("cap1"))
        entities = [cap1, cap2]
        resolve_graph_edges(entities)
        return FeatureMap(metadata=FeatureMapMetadata(), entities=entities)

    def test_unscoped_function_clusters_graph(self, feature_map: FeatureMap) -> None:
        @styling.group_tasks
        def group_all(
            entities: Sequence[EntityProtocol], context: StylingContext
        ) -> dict[str | None, list[EntityProtocol]]:
            return {"Everything": list(entities)}

        dot = GraphGenerator(feature_map).generate(GraphView.ALL)

        clusters, top_level = _parse_clusters(dot)
        assert clusters == {"Everything": ["cap1", "cap2"]}
        assert top_level == []

    def test_gantt_scoped_function_does_not_cluster_graph(self, feature_map: FeatureMap) -> None:
        @styling.group_tasks(formats=["gantt"])
        def group_all(
            entities: Sequence[EntityProtocol], context: StylingContext
        ) -> dict[str | None, list[EntityProtocol]]:
            return {"Everything": list(entities)}

        dot = GraphGenerator(feature_map).generate(GraphView.ALL)

        assert "subgraph cluster_" not in dot

    def test_user_function_overrides_builtin(self, feature_map: FeatureMap) -> None:
        @styling.group_tasks(formats=["graph"])
        def group_all(
            entities: Sequence[EntityProtocol], context: StylingContext
        ) -> dict[str | None, list[EntityProtocol]]:
            return {"Everything": list(entities)}

        register_builtin_clustering("meta.repo")
        dot = GraphGenerator(feature_map).generate(GraphView.ALL)

        clusters, _ = _parse_clusters(dot)
        assert clusters == {"Everything": ["cap1", "cap2"]}

    def test_style_tag_gating_applies(self, feature_map: FeatureMap) -> None:
        @styling.group_tasks(tags=["deep"])
        def group_all(
            entities: Sequence[EntityProtocol], context: StylingContext
        ) -> dict[str | None, list[EntityProtocol]]:
            return {"Everything": list(entities)}

        inactive = styling.create_styling_context(feature_map, output_format="graph")
        assert "subgraph cluster_" not in GraphGenerator(feature_map, inactive).generate()

        active = styling.create_styling_context(
            feature_map, output_format="graph", style_tags={"deep"}
        )
        assert "subgraph cluster_" in GraphGenerator(feature_map, active).generate()

    def test_omitted_entity_gets_no_node_definition(self, feature_map: FeatureMap) -> None:
        @styling.group_tasks(formats=["graph"])
        def group_first_only(
            entities: Sequence[EntityProtocol], context: StylingContext
        ) -> dict[str | None, list[EntityProtocol]]:
            return {"Partial": [e for e in entities if e.id == "cap1"]}

        dot = GraphGenerator(feature_map).generate(GraphView.ALL)

        assert "cap2 [label=" not in dot
        assert "cap1 -> cap2;" in dot

    def test_active_grouping_func_reports_the_winner(self, feature_map: FeatureMap) -> None:
        context = styling.create_styling_context(feature_map, output_format="graph")
        assert styling.active_grouping_func(context) is None

        clustering = register_builtin_clustering("meta.repo")
        assert clustering is not None
        assert styling.active_grouping_func(context) is clustering.func

        @styling.group_tasks(formats=["graph"])
        def group_all(
            entities: Sequence[EntityProtocol], context: StylingContext
        ) -> dict[str | None, list[EntityProtocol]]:
            return {"Everything": list(entities)}

        assert styling.active_grouping_func(context) is group_all

    def test_unscoped_sort_function_does_not_reorder_graph_nodes(
        self, feature_map: FeatureMap
    ) -> None:
        """Graph rendering never consults sort_tasks, scoped or not."""

        @styling.sort_tasks
        def reverse_by_id(
            entities: Sequence[EntityProtocol], context: StylingContext
        ) -> list[EntityProtocol]:
            return sorted(entities, key=lambda e: e.id, reverse=True)

        dot = GraphGenerator(feature_map).generate(GraphView.ALL)

        _, top_level = _parse_clusters(dot)
        assert top_level == ["cap1", "cap2"]

    def test_registered_clustering_does_not_affect_gantt(self, feature_map: FeatureMap) -> None:
        register_builtin_clustering("meta.repo")
        context = styling.create_styling_context(feature_map, output_format="gantt")

        groups = styling.apply_task_grouping(feature_map.entities, context)

        assert list(groups) == [None]


_CLUSTER_FM = """\
metadata:
  version: '1.0'
entities:
  cap1:
    type: capability
    name: Cap One
    description: first
    tags: [infra]
    meta:
      repo: alpha
  cap2:
    type: capability
    name: Cap Two
    description: second
    requires: [cap1]
    tags: [legacy]
    meta:
      repo: [beta, alpha]
  story1:
    type: user_story
    name: Story One
    description: no repo
    requires: [cap2]
"""

_HETEROGENEOUS_FM = """\
metadata:
  version: '1.0'
entities:
  cap1:
    type: capability
    name: Cap One
    description: scalar repo, resolves first
    meta:
      repo: alpha
  cap2:
    type: capability
    name: Cap Two
    description: nested repo, only reachable at generation time
    requires: [cap1]
    meta:
      repo:
        name: gamma
"""

_TAG_SCOPED_FM = """\
metadata:
  version: '1.0'
entities:
  orphan:
    type: capability
    name: Orphan
    description: dict repo, no edges, excluded by the infra tag closure
    tags: [other]
    meta:
      repo:
        name: gamma
  cap1:
    type: capability
    name: Cap One
    description: scalar repo
    tags: [infra]
    meta:
      repo: alpha
"""


def _write_fm(tmp_path: Path) -> Path:
    """Write the clustering test feature map and return its path."""
    path = tmp_path / "fm.yaml"
    path.write_text(_CLUSTER_FM)
    return path


def _write_heterogeneous_fm(tmp_path: Path) -> Path:
    """Write a feature map whose first entity resolves a scalar and second a dict."""
    path = tmp_path / "hetero.yaml"
    path.write_text(_HETEROGENEOUS_FM)
    return path


def _write_tag_scoped_fm(tmp_path: Path) -> Path:
    """Write a feature map whose dict-valued entity is unconnected and declared first."""
    path = tmp_path / "tag_scoped.yaml"
    path.write_text(_TAG_SCOPED_FM)
    return path


def _write_grouping_style_file(tmp_path: Path) -> Path:
    """Write a style file with a graph grouping function that outranks the built-in."""
    path = tmp_path / "style.py"
    path.write_text(
        """\
from mouc import styling


@styling.group_tasks(formats=['graph'])
def group_all(entities, context):
    return {'Everything': list(entities)}
"""
    )
    return path


class TestClusterByCli:
    """Test the --cluster-by CLI option."""

    def test_clusters_output(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["graph", str(_write_fm(tmp_path)), "--cluster-by", "meta.repo"]
        )

        assert result.exit_code == 0, result.output
        assert 'label="alpha";' in result.output
        assert 'label="beta";' in result.output
        assert "subgraph cluster_0" in result.output

    def test_rejected_with_timeline_view(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["graph", str(_write_fm(tmp_path)), "--cluster-by", "meta.repo", "--view", "timeline"],
        )

        assert result.exit_code == 1
        assert "Error: --cluster-by cannot be combined with --view timeline" in result.output

    def test_invalid_path_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["graph", str(_write_fm(tmp_path)), "--cluster-by", "mata.repo"]
        )

        assert result.exit_code == 1
        assert "'mata' is not an entity field" in result.output

    def test_empty_segment_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["graph", str(_write_fm(tmp_path)), "--cluster-by", "meta."])

        assert result.exit_code == 1
        assert "empty path segment" in result.output

    def test_non_scalar_value_errors(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["graph", str(_write_fm(tmp_path)), "--cluster-by", "meta"])

        assert result.exit_code == 1
        assert "Entity 'cap1'" in result.output
        assert "'meta' resolves to a dict" in result.output

    def test_non_scalar_value_errors_from_generation(self, tmp_path: Path) -> None:
        """Dict values that escape early validation are still caught at generation."""
        result = runner.invoke(
            app,
            ["graph", str(_write_heterogeneous_fm(tmp_path)), "--cluster-by", "meta.repo"],
        )

        assert result.exit_code == 1
        assert "Error: Entity 'cap2'" in result.output
        assert "'meta.repo' resolves to a dict" in result.output

    def test_non_scalar_value_outside_filter_is_inert(self, tmp_path: Path) -> None:
        """An entity excluded by --tags never reaches grouping, so its bad value cannot abort."""
        result = runner.invoke(
            app,
            [
                "graph",
                str(_write_tag_scoped_fm(tmp_path)),
                "--cluster-by",
                "meta.repo",
                "--tags",
                "infra",
            ],
        )

        assert result.exit_code == 0, result.output
        assert 'label="alpha";' in result.output
        assert "Orphan" not in result.output

    def test_non_scalar_value_inside_filter_errors(self, tmp_path: Path) -> None:
        """The same bad entity aborts when it is part of the rendered graph."""
        result = runner.invoke(
            app, ["graph", str(_write_tag_scoped_fm(tmp_path)), "--cluster-by", "meta.repo"]
        )

        assert result.exit_code == 1
        assert "Error: Entity 'orphan'" in result.output

    def test_filtered_view_clusters_surviving_entities(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "graph",
                str(_write_fm(tmp_path)),
                "--view",
                "filtered",
                "--tags",
                "infra,!legacy",
                "--cluster-by",
                "meta.repo",
            ],
        )

        assert result.exit_code == 0, result.output
        assert 'label="alpha";' in result.output
        assert "Cap Two" not in result.output
        assert 'label="beta";' not in result.output

    def test_no_match_warns_and_succeeds(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["graph", str(_write_fm(tmp_path)), "--cluster-by", "meta.nothing"]
        )

        assert result.exit_code == 0
        assert "warning: --cluster-by matched no entities" in result.output
        assert "subgraph cluster_" not in result.output

    def test_combined_with_tags(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "graph",
                str(_write_fm(tmp_path)),
                "--cluster-by",
                "meta.repo",
                "--tags",
                "infra",
                "--tags-direction",
                "up",
            ],
        )

        assert result.exit_code == 0, result.output
        assert 'label="alpha";' in result.output
        assert "Cap Two" not in result.output
        assert 'label="beta";' not in result.output

    def test_user_override_suppresses_no_match_warning(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "graph",
                str(_write_fm(tmp_path)),
                "--cluster-by",
                "meta.nothing",
                "--style-file",
                str(_write_grouping_style_file(tmp_path)),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "warning: --cluster-by matched no entities" not in result.output
        assert 'label="Everything";' in result.output

    def test_user_override_suppresses_non_scalar_error(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "graph",
                str(_write_fm(tmp_path)),
                "--cluster-by",
                "requires",
                "--style-file",
                str(_write_grouping_style_file(tmp_path)),
            ],
        )

        assert result.exit_code == 0, result.output
        assert 'label="Everything";' in result.output

    def test_stale_builtin_cleared_on_next_invocation(self, tmp_path: Path) -> None:
        fm = _write_fm(tmp_path)
        clustered = runner.invoke(app, ["graph", str(fm), "--cluster-by", "meta.repo"])
        flat = runner.invoke(app, ["graph", str(fm)])

        assert "subgraph cluster_" in clustered.output
        assert flat.exit_code == 0
        assert "subgraph cluster_" not in flat.output
