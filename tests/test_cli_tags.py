"""CLI-level tests for --tags and --tags-direction across graph/doc/gantt/schedule."""

import re
from pathlib import Path

from typer.testing import CliRunner

from mouc.cli import app

runner = CliRunner()

# Feature map YAML used by most tests; uses real entities with known tags.
_EXAMPLE_FM = "examples/feature_map.yaml"


def _make_simple_fm(tmp_path: Path, extra: str = "") -> Path:
    """Write a tiny feature map with two chained entities for isolation tests."""
    p = tmp_path / "fm.yaml"
    p.write_text(
        f"""\
metadata:
  version: '1.0'
entities:
  upstream:
    type: capability
    name: Upstream Task
    description: upstream
    tags: [target]
    meta:
      effort: 1d
      resources: [alice]
  downstream:
    type: capability
    name: Downstream Task
    description: downstream
    meta:
      effort: 1d
      resources: [alice]
    requires: [upstream]
  unrelated:
    type: capability
    name: Unrelated Task
    description: unrelated
    tags: [other]
    meta:
      effort: 1d
      resources: [alice]
  archived_item:
    type: capability
    name: Archived Task
    description: archived
    tags: [archived]
    meta:
      effort: 1d
      resources: [alice]
{extra}
"""
    )
    return p


def _make_phased_fm(tmp_path: Path) -> Path:
    """Feature map with a workflow-expanded entity; stdlib workflow creates phase siblings."""
    p = tmp_path / "phased.yaml"
    p.write_text(
        """\
metadata:
  version: '1.0'
entities:
  parent:
    type: capability
    name: Parent Feature
    description: parent with phases
    tags: [target]
    workflow: design_impl
    meta:
      effort: 1d
      resources: [alice]
      design:
        effort: 1d
        resources: [alice]
"""
    )
    # Write mouc_config.yaml so the loader enables stdlib workflows.
    config = tmp_path / "mouc_config.yaml"
    config.write_text(
        """\
resources:
  - name: alice
workflows:
  stdlib: true
"""
    )
    return p


# ============================================================================
# graph command
# ============================================================================


class TestGraphTags:
    def test_positive_match_all_view(self, tmp_path: Path) -> None:
        """--tags foo with default --view all includes closure."""
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(app, ["graph", str(fm), "--tags", "target"])
        assert result.exit_code == 0, result.output
        assert "Upstream Task" in result.output
        assert "Downstream Task" in result.output  # in closure
        # archived_item and unrelated are unreachable from target closure
        assert "Unrelated Task" not in result.output
        assert "Archived Task" not in result.output

    def test_negation_drops_reachable_entity(self, tmp_path: Path) -> None:
        """!archived excludes archived_item even when it has an edge into the closure."""
        # Give archived_item an edge so it would appear without the filter.
        fm = _make_simple_fm(
            tmp_path,
            extra="""\
  connected_archived:
    type: capability
    name: Connected Archived
    description: archived but reachable
    tags: [target, archived]
    meta:
      effort: 1d
      resources: [alice]
    requires: [upstream]
""",
        )
        result = runner.invoke(app, ["graph", str(fm), "--tags", "target", "--tags", "!archived"])
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        # connected_archived is in the closure (tagged target) but excluded by !archived
        assert "Connected Archived" not in result.output

    def test_negation_excludes(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(app, ["graph", str(fm), "--tags", "!archived"])
        assert result.exit_code == 0
        assert "Archived Task" not in result.output

    def test_repeated_form_equivalent_to_comma(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        r1 = runner.invoke(app, ["graph", str(fm), "--tags", "target", "--tags", "other"])
        r2 = runner.invoke(app, ["graph", str(fm), "--tags", "target,other"])
        assert r1.exit_code == 0
        assert r2.exit_code == 0
        assert r1.output == r2.output

    def test_empty_match_warning_exit_0(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(app, ["graph", str(fm), "--tags", "nonexistent_xyz"])
        assert result.exit_code == 0
        assert "warning: --tags matched no entities" in result.output

    def test_tags_direction_up(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["graph", str(fm), "--tags", "target", "--tags-direction", "up"]
        )
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        # upstream has no requires, so closure = just upstream itself
        assert "Downstream Task" not in result.output

    def test_tags_direction_down(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["graph", str(fm), "--tags", "target", "--tags-direction", "down"]
        )
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        assert "Downstream Task" in result.output

    def test_view_filtered_with_positive_tags(self, tmp_path: Path) -> None:
        """--view filtered with --tags keeps one-hop semantics."""
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(app, ["graph", str(fm), "--view", "filtered", "--tags", "target"])
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        assert "Downstream Task" in result.output  # one-hop neighbor

    def test_view_filtered_negation_only_rejected(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(app, ["graph", str(fm), "--view", "filtered", "--tags", "!archived"])
        assert result.exit_code == 1
        assert "--view filtered requires at least one positive --tags token" in result.output

    def test_view_filtered_with_negation_drops_neighbor(self, tmp_path: Path) -> None:
        """Negated one-hop neighbors of a matched entity are not rendered."""
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["graph", str(fm), "--view", "filtered", "--tags", "target,!archived"]
        )
        assert result.exit_code == 0
        assert "Archived Task" not in result.output

    def test_phase_sibling_auto_include(self, tmp_path: Path) -> None:
        """Matching a workflow-parent entity auto-includes its phase siblings."""
        fm = _make_phased_fm(tmp_path)
        result = runner.invoke(app, ["graph", str(fm), "--tags", "target"])
        assert result.exit_code == 0, result.output
        # parent is tagged target (impl phase); design phase sibling must also appear
        assert "Parent Feature" in result.output  # the impl phase (parent entity)
        assert "Design" in result.output  # the design phase sibling

    def test_no_tags_is_idempotent(self) -> None:
        """Without --tags, graph output is idempotent across invocations."""
        r1 = runner.invoke(app, ["graph", _EXAMPLE_FM])
        r2 = runner.invoke(app, ["graph", _EXAMPLE_FM])
        assert r1.exit_code == 0
        assert r1.output == r2.output

    def test_critical_path_with_tags_excludes_ancestors(self, tmp_path: Path) -> None:
        """--view critical-path + --tags: excluded ancestors don't render as orphans."""
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app,
            [
                "graph",
                str(fm),
                "--view",
                "critical-path",
                "--target",
                "downstream",
                "--tags",
                "!archived",
            ],
        )
        assert result.exit_code == 0
        assert "Archived Task" not in result.output


# ============================================================================
# doc command
# ============================================================================


class TestDocTags:
    def test_positive_match(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(app, ["doc", str(fm), "--tags", "target"])
        assert result.exit_code == 0, result.output
        assert "Upstream Task" in result.output
        assert "Downstream Task" in result.output
        assert "Unrelated Task" not in result.output

    def test_negation(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(app, ["doc", str(fm), "--tags", "!archived"])
        assert result.exit_code == 0
        assert "Archived Task" not in result.output

    def test_repeated_form(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        r1 = runner.invoke(app, ["doc", str(fm), "--tags", "target", "--tags", "other"])
        r2 = runner.invoke(app, ["doc", str(fm), "--tags", "target,other"])
        assert r1.exit_code == 0
        assert r2.exit_code == 0
        assert r1.output == r2.output

    def test_empty_match_warning(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(app, ["doc", str(fm), "--tags", "nonexistent_xyz"])
        assert result.exit_code == 0
        assert "warning: --tags matched no entities" in result.output

    def test_filtered_reference_marked(self, tmp_path: Path) -> None:
        """References from included to excluded entities use (filtered) marker."""
        fm = _make_simple_fm(tmp_path)
        # target selects upstream; closure adds downstream; negation removes upstream.
        # downstream is rendered but its requires-upstream is excluded -> (filtered) marker.
        result = runner.invoke(app, ["doc", str(fm), "--tags", "target,!target"])
        assert result.exit_code == 0
        assert "(filtered)" in result.output

    def test_tags_direction_up(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(app, ["doc", str(fm), "--tags", "target", "--tags-direction", "up"])
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        # Downstream may appear as a (filtered) cross-reference but not as an entity section.
        assert "#### Downstream Task" not in result.output
        assert "### Downstream Task" not in result.output

    def test_tags_direction_down(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["doc", str(fm), "--tags", "target", "--tags-direction", "down"]
        )
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        assert "Downstream Task" in result.output  # downstream of target

    def test_no_tags_is_idempotent(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        r1 = runner.invoke(app, ["doc", str(fm)])
        r2 = runner.invoke(app, ["doc", str(fm)])
        assert r1.exit_code == 0
        assert r1.output == r2.output


# ============================================================================
# gantt command
# ============================================================================


class TestGanttTags:
    def test_positive_match(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["gantt", str(fm), "--current-date", "2025-01-01", "--tags", "target"]
        )
        assert result.exit_code == 0, result.output
        assert "Upstream Task" in result.output
        assert "Downstream Task" in result.output
        assert "Unrelated Task" not in result.output

    def test_negation(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["gantt", str(fm), "--current-date", "2025-01-01", "--tags", "!archived"]
        )
        assert result.exit_code == 0
        assert "Archived Task" not in result.output

    def test_repeated_form(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        r1 = runner.invoke(
            app,
            [
                "gantt",
                str(fm),
                "--current-date",
                "2025-01-01",
                "--tags",
                "target",
                "--tags",
                "other",
            ],
        )
        r2 = runner.invoke(
            app,
            ["gantt", str(fm), "--current-date", "2025-01-01", "--tags", "target,other"],
        )
        assert r1.exit_code == 0
        assert r2.exit_code == 0
        assert r1.output == r2.output

    def test_empty_match_warning(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["gantt", str(fm), "--current-date", "2025-01-01", "--tags", "nonexistent"]
        )
        assert result.exit_code == 0
        assert "warning: --tags matched no entities" in result.output

    def test_scheduled_dates_consistent_with_unfiltered(self, tmp_path: Path) -> None:
        """Dates in filtered output must equal unfiltered run for same entities."""
        fm = _make_simple_fm(tmp_path)
        unfiltered = runner.invoke(app, ["gantt", str(fm), "--current-date", "2025-01-01"])
        filtered = runner.invoke(
            app, ["gantt", str(fm), "--current-date", "2025-01-01", "--tags", "target"]
        )
        assert unfiltered.exit_code == 0
        assert filtered.exit_code == 0
        # Both outputs should contain the same start date for Upstream Task
        unfiltered_dates = re.findall(r"\d{4}-\d{2}-\d{2}", unfiltered.output)
        filtered_dates = re.findall(r"\d{4}-\d{2}-\d{2}", filtered.output)
        # Filtered output dates are a subset of unfiltered dates
        assert all(d in unfiltered_dates for d in filtered_dates)

    def test_tags_direction_up(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app,
            [
                "gantt",
                str(fm),
                "--current-date",
                "2025-01-01",
                "--tags",
                "target",
                "--tags-direction",
                "up",
            ],
        )
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        # upstream has no requires, so closure = just upstream itself
        assert "Downstream Task" not in result.output

    def test_tags_direction_down(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app,
            [
                "gantt",
                str(fm),
                "--current-date",
                "2025-01-01",
                "--tags",
                "target",
                "--tags-direction",
                "down",
            ],
        )
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        assert "Downstream Task" in result.output

    def test_no_tags_is_idempotent(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        r1 = runner.invoke(app, ["gantt", str(fm), "--current-date", "2025-01-01"])
        r2 = runner.invoke(app, ["gantt", str(fm), "--current-date", "2025-01-01"])
        assert r1.exit_code == 0
        assert r1.output == r2.output


# ============================================================================
# schedule command
# ============================================================================


class TestScheduleTags:
    def test_positive_match(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["schedule", str(fm), "--current-date", "2025-01-01", "--tags", "target"]
        )
        assert result.exit_code == 0, result.output
        assert "Upstream Task" in result.output
        assert "Downstream Task" in result.output
        assert "Unrelated Task" not in result.output

    def test_negation(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["schedule", str(fm), "--current-date", "2025-01-01", "--tags", "!archived"]
        )
        assert result.exit_code == 0
        assert "Archived Task" not in result.output

    def test_repeated_form(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        r1 = runner.invoke(
            app,
            [
                "schedule",
                str(fm),
                "--current-date",
                "2025-01-01",
                "--tags",
                "target",
                "--tags",
                "other",
            ],
        )
        r2 = runner.invoke(
            app,
            ["schedule", str(fm), "--current-date", "2025-01-01", "--tags", "target,other"],
        )
        assert r1.exit_code == 0
        assert r2.exit_code == 0
        assert r1.output == r2.output

    def test_empty_match_warning(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app, ["schedule", str(fm), "--current-date", "2025-01-01", "--tags", "nonexistent"]
        )
        assert result.exit_code == 0
        assert "warning: --tags matched no entities" in result.output

    def test_scheduled_dates_consistent(self, tmp_path: Path) -> None:
        """Filtered schedule shows same dates as unfiltered for same entities."""
        fm = _make_simple_fm(tmp_path)
        unfiltered = runner.invoke(app, ["schedule", str(fm), "--current-date", "2025-01-01"])
        filtered = runner.invoke(
            app, ["schedule", str(fm), "--current-date", "2025-01-01", "--tags", "target"]
        )
        assert unfiltered.exit_code == 0
        assert filtered.exit_code == 0
        # Both contain the start/end date lines for Upstream Task
        unfilt_starts = {
            m.group(1) for m in re.finditer(r"Estimated Start:\s+(\S+)", unfiltered.output)
        }
        filt_starts = {
            m.group(1) for m in re.finditer(r"Estimated Start:\s+(\S+)", filtered.output)
        }
        assert filt_starts <= unfilt_starts

    def test_output_lock_unfiltered(self, tmp_path: Path) -> None:
        """--output-lock produces full schedule even with --tags."""
        fm = _make_simple_fm(tmp_path)
        lock_path = tmp_path / "out.lock.yaml"
        result = runner.invoke(
            app,
            [
                "schedule",
                str(fm),
                "--current-date",
                "2025-01-01",
                "--tags",
                "target",
                "--output-lock",
                str(lock_path),
            ],
        )
        assert result.exit_code == 0
        assert lock_path.exists()
        lock_content = lock_path.read_text()
        # Lock file should contain all scheduled entities (full schedule)
        assert "upstream" in lock_content
        assert "downstream" in lock_content

    def test_csv_output_with_tags(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        csv_path = tmp_path / "out.csv"
        result = runner.invoke(
            app,
            [
                "schedule",
                str(fm),
                "--current-date",
                "2025-01-01",
                "--tags",
                "target",
                "--output-csv",
                str(csv_path),
            ],
        )
        assert result.exit_code == 0
        assert csv_path.exists()
        csv_content = csv_path.read_text()
        assert "upstream" in csv_content
        # downstream is in the closure of target (required by upstream)
        assert "downstream" in csv_content
        # Unrelated and archived not in closure
        assert "unrelated" not in csv_content
        assert "archived" not in csv_content

    def test_no_tags_is_idempotent(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        r1 = runner.invoke(app, ["schedule", str(fm), "--current-date", "2025-01-01"])
        r2 = runner.invoke(app, ["schedule", str(fm), "--current-date", "2025-01-01"])
        assert r1.exit_code == 0
        assert r1.output == r2.output

    def test_tags_direction_up(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app,
            [
                "schedule",
                str(fm),
                "--current-date",
                "2025-01-01",
                "--tags",
                "target",
                "--tags-direction",
                "up",
            ],
        )
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        assert "Downstream Task" not in result.output

    def test_tags_direction_down(self, tmp_path: Path) -> None:
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app,
            [
                "schedule",
                str(fm),
                "--current-date",
                "2025-01-01",
                "--tags",
                "target",
                "--tags-direction",
                "down",
            ],
        )
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        assert "Downstream Task" in result.output


# ============================================================================
# Combined --tags + --style-tags
# ============================================================================


class TestTagsCombinedWithStyleTags:
    """Both --tags and --style-tags may be combined; --tags applies first."""

    def test_graph_combined(self, tmp_path: Path) -> None:
        style_file = tmp_path / "style.py"
        style_file.write_text(
            """\
from mouc import styling
from collections.abc import Sequence

@styling.filter_entity(tags=['myview'])
def extra_filter(entities, ctx):
    return [e for e in entities if e.id != 'archived_item']
"""
        )
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app,
            [
                "graph",
                str(fm),
                "--tags",
                "target",
                "--style-tags",
                "myview",
                "--style-file",
                str(style_file),
            ],
        )
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        assert "Archived Task" not in result.output

    def test_gantt_combined(self, tmp_path: Path) -> None:
        style_file = tmp_path / "style.py"
        style_file.write_text(
            """\
from mouc import styling
from collections.abc import Sequence

@styling.filter_entity(tags=['myview'])
def extra_filter(entities, ctx):
    return [e for e in entities if e.id != 'archived_item']
"""
        )
        fm = _make_simple_fm(tmp_path)
        result = runner.invoke(
            app,
            [
                "gantt",
                str(fm),
                "--current-date",
                "2025-01-01",
                "--tags",
                "target",
                "--style-tags",
                "myview",
                "--style-file",
                str(style_file),
            ],
        )
        assert result.exit_code == 0
        assert "Upstream Task" in result.output
        assert "Archived Task" not in result.output
