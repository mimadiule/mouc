"""Unit tests for tag_filter module."""

import pytest

from mouc.models import Dependency, Entity, FeatureMap, FeatureMapMetadata
from mouc.parser import resolve_graph_edges
from mouc.tag_filter import parse_tag_options, select_entities, selection_is_empty
from tests.conftest import deps


def _make_entity(eid: str, tags: list[str] | None = None, **kwargs: object) -> Entity:
    return Entity(
        type="capability",
        id=eid,
        name=eid,
        description="",
        tags=tags or [],
        **kwargs,  # type: ignore[arg-type]
    )


def _fm(*entities: Entity) -> FeatureMap:
    elist = list(entities)
    resolve_graph_edges(elist)
    return FeatureMap(metadata=FeatureMapMetadata(), entities=elist)


# ---------------------------------------------------------------------------
# parse_tag_options
# ---------------------------------------------------------------------------


class TestParseTagOptions:
    def test_none_input_is_empty(self) -> None:
        spec = parse_tag_options(None)
        assert spec.is_empty
        assert spec.include == frozenset()
        assert spec.exclude == frozenset()
        assert spec.direction == "both"

    def test_empty_list_is_empty(self) -> None:
        spec = parse_tag_options([])
        assert spec.is_empty

    def test_single_positive(self) -> None:
        spec = parse_tag_options(["foo"])
        assert spec.include == frozenset({"foo"})
        assert spec.exclude == frozenset()
        assert not spec.is_empty

    def test_negation_prefix(self) -> None:
        spec = parse_tag_options(["!bar"])
        assert spec.include == frozenset()
        assert spec.exclude == frozenset({"bar"})
        assert not spec.is_empty

    def test_comma_separated(self) -> None:
        spec = parse_tag_options(["a,b,!c"])
        assert spec.include == frozenset({"a", "b"})
        assert spec.exclude == frozenset({"c"})

    def test_repeated_args(self) -> None:
        spec = parse_tag_options(["a", "b", "!c"])
        assert spec.include == frozenset({"a", "b"})
        assert spec.exclude == frozenset({"c"})

    def test_mixed_comma_and_repeated(self) -> None:
        spec = parse_tag_options(["a,b", "c"])
        assert spec.include == frozenset({"a", "b", "c"})

    def test_whitespace_stripped(self) -> None:
        spec = parse_tag_options([" a , b "])
        assert spec.include == frozenset({"a", "b"})

    def test_empty_tokens_dropped(self) -> None:
        spec = parse_tag_options(["a,,b"])
        assert spec.include == frozenset({"a", "b"})

    def test_bare_exclamation_raises(self) -> None:
        with pytest.raises(ValueError, match="must be followed by a tag name"):
            parse_tag_options(["!"])

    def test_direction_up(self) -> None:
        spec = parse_tag_options(["foo"], direction="up")
        assert spec.direction == "up"

    def test_direction_down(self) -> None:
        spec = parse_tag_options(["foo"], direction="down")
        assert spec.direction == "down"

    def test_direction_both_default(self) -> None:
        spec = parse_tag_options(["foo"])
        assert spec.direction == "both"


# ---------------------------------------------------------------------------
# select_entities
# ---------------------------------------------------------------------------


class TestSelectEntities:
    def test_empty_spec_returns_all(self) -> None:
        e1 = _make_entity("a")
        e2 = _make_entity("b")
        fm = _fm(e1, e2)
        spec = parse_tag_options(None)
        result = select_entities(fm, spec)
        assert [e.id for e in result] == ["a", "b"]

    def test_single_positive_no_closure(self) -> None:
        e1 = _make_entity("a", tags=["foo"])
        e2 = _make_entity("b")
        fm = _fm(e1, e2)
        spec = parse_tag_options(["foo"])
        result = select_entities(fm, spec)
        assert {e.id for e in result} == {"a"}

    def test_positive_with_upstream_downstream(self) -> None:
        # a -> b (tagged) -> c
        a = _make_entity("a")
        b = _make_entity("b", tags=["target"], requires=deps("a"))
        c = _make_entity("c", requires=deps("b"))
        fm = _fm(a, b, c)
        spec = parse_tag_options(["target"])
        result = select_entities(fm, spec)
        assert {e.id for e in result} == {"a", "b", "c"}

    def test_direction_up_only(self) -> None:
        # a -> b (tagged) -> c
        a = _make_entity("a")
        b = _make_entity("b", tags=["target"], requires=deps("a"))
        c = _make_entity("c", requires=deps("b"))
        fm = _fm(a, b, c)
        spec = parse_tag_options(["target"], direction="up")
        result = select_entities(fm, spec)
        assert {e.id for e in result} == {"a", "b"}

    def test_direction_down_only(self) -> None:
        # a -> b (tagged) -> c
        a = _make_entity("a")
        b = _make_entity("b", tags=["target"], requires=deps("a"))
        c = _make_entity("c", requires=deps("b"))
        fm = _fm(a, b, c)
        spec = parse_tag_options(["target"], direction="down")
        result = select_entities(fm, spec)
        assert {e.id for e in result} == {"b", "c"}

    def test_both_direction_does_not_walk_upstream_from_downstream(self) -> None:
        """Regression: direction=both must not pull in entities upstream of downstream-reached nodes.

        Topology: alpha->{beta,gamma}; beta->delta; gamma->epsilon; delta,epsilon->zeta
        Tag 'backend' on gamma and epsilon only.
        direction=both: direct={gamma,epsilon}
          up(direct)   = {alpha, gamma, epsilon}
          down(direct) = {gamma, epsilon, zeta}
          expected     = {alpha, gamma, epsilon, zeta}
          NOT expected: beta (upstream of zeta via delta) or delta (upstream of zeta).
        """
        alpha = _make_entity("alpha")
        beta = _make_entity("beta", requires=deps("alpha"))
        gamma = _make_entity("gamma", tags=["backend"], requires=deps("alpha"))
        delta = _make_entity("delta", requires=deps("beta"))
        epsilon = _make_entity("epsilon", tags=["backend"], requires=deps("gamma"))
        zeta = _make_entity("zeta", requires=deps("delta", "epsilon"))
        fm = _fm(alpha, beta, gamma, delta, epsilon, zeta)
        spec = parse_tag_options(["backend"])
        result = select_entities(fm, spec)
        assert {e.id for e in result} == {"alpha", "gamma", "epsilon", "zeta"}

    def test_cycle_terminates(self) -> None:
        # a -> b -> a (cycle), both tagged
        a = Entity(
            type="capability",
            id="a",
            name="a",
            description="",
            tags=["foo"],
            requires={Dependency(entity_id="b")},
        )
        b = Entity(
            type="capability",
            id="b",
            name="b",
            description="",
            tags=["foo"],
            requires={Dependency(entity_id="a")},
        )
        fm = FeatureMap(metadata=FeatureMapMetadata(), entities=[a, b])
        spec = parse_tag_options(["foo"])
        result = select_entities(fm, spec)
        assert {e.id for e in result} == {"a", "b"}

    def test_negation_only(self) -> None:
        e1 = _make_entity("a", tags=["archived"])
        e2 = _make_entity("b")
        fm = _fm(e1, e2)
        spec = parse_tag_options(["!archived"])
        result = select_entities(fm, spec)
        assert {e.id for e in result} == {"b"}

    def test_positive_and_negation_closure_excluded(self) -> None:
        # a (tagged=target) -> b (tagged=archived)
        a = _make_entity("a", tags=["target"])
        b = _make_entity("b", tags=["archived"], requires=deps("a"))
        c = _make_entity("c")
        fm = _fm(a, b, c)
        spec = parse_tag_options(["target", "!archived"])
        result = select_entities(fm, spec)
        # b would be pulled in by downstream closure but is excluded by !archived
        assert {e.id for e in result} == {"a"}

    def test_closure_through_excluded_entity_retains_downstream(self) -> None:
        """Closure runs before negation: entities reachable through excluded entity are kept."""
        # a(target) -> b(archived) -> d
        # With spec [target, !archived]: closure = {a, b, d}; negation removes b; result = {a, d}
        a = _make_entity("a", tags=["target"])
        b = _make_entity("b", tags=["archived"], requires=deps("a"))
        d = _make_entity("d", requires=deps("b"))
        fm = _fm(a, b, d)
        spec = parse_tag_options(["target", "!archived"])
        result = select_entities(fm, spec)
        assert {e.id for e in result} == {"a", "d"}

    def test_no_match_returns_empty(self) -> None:
        e1 = _make_entity("a")
        fm = _fm(e1)
        spec = parse_tag_options(["nonexistent"])
        result = select_entities(fm, spec)
        assert result == []

    def test_preserves_input_order(self) -> None:
        # Create entities in a specific order; result should match that order
        entities = [_make_entity(str(i), tags=["x"]) for i in range(5)]
        fm = _fm(*entities)
        spec = parse_tag_options(["x"])
        result = select_entities(fm, spec)
        assert [e.id for e in result] == [str(i) for i in range(5)]

    def test_sibling_phase_auto_include_case_a(self) -> None:
        """When a phase entity is matched, all sibling phases are included."""
        parent = _make_entity("parent", tags=["target"])
        phase_a = Entity(
            type="capability",
            id="phase_a",
            name="Phase A",
            description="",
            phase_of=("parent", "design"),
        )
        phase_b = Entity(
            type="capability",
            id="phase_b",
            name="Phase B",
            description="",
            phase_of=("parent", "implement"),
            tags=["target"],
        )
        fm = FeatureMap(metadata=FeatureMapMetadata(), entities=[parent, phase_a, phase_b])
        spec = parse_tag_options(["target"])
        result = select_entities(fm, spec)
        # phase_b tagged, parent tagged; both phase siblings should be included
        assert {e.id for e in result} == {"parent", "phase_a", "phase_b"}

    def test_sibling_phase_auto_include_case_b(self) -> None:
        """When a parent entity is matched, its phase children are included."""
        parent = _make_entity("parent", tags=["target"])
        phase_a = Entity(
            type="capability",
            id="phase_a",
            name="Phase A",
            description="",
            phase_of=("parent", "design"),
        )
        phase_b = Entity(
            type="capability",
            id="phase_b",
            name="Phase B",
            description="",
            phase_of=("parent", "implement"),
        )
        fm = FeatureMap(metadata=FeatureMapMetadata(), entities=[parent, phase_a, phase_b])
        spec = parse_tag_options(["target"])
        result = select_entities(fm, spec)
        assert {e.id for e in result} == {"parent", "phase_a", "phase_b"}

    def test_sibling_phase_negation_removes_sibling(self) -> None:
        """Negation still removes a sibling phase even after sibling expansion."""
        parent = _make_entity("parent", tags=["target"])
        phase_a = Entity(
            type="capability",
            id="phase_a",
            name="Phase A",
            description="",
            phase_of=("parent", "design"),
        )
        phase_b = Entity(
            type="capability",
            id="phase_b",
            name="Phase B",
            description="",
            phase_of=("parent", "implement"),
            tags=["archived"],
        )
        fm = FeatureMap(metadata=FeatureMapMetadata(), entities=[parent, phase_a, phase_b])
        spec = parse_tag_options(["target", "!archived"])
        result = select_entities(fm, spec)
        assert "phase_b" not in {e.id for e in result}
        assert "parent" in {e.id for e in result}
        assert "phase_a" in {e.id for e in result}


# ---------------------------------------------------------------------------
# selection_is_empty
# ---------------------------------------------------------------------------


class TestSelectionIsEmpty:
    def test_empty_spec_never_empty(self) -> None:
        spec = parse_tag_options(None)
        assert not selection_is_empty([], spec)

    def test_non_empty_spec_no_results(self) -> None:
        spec = parse_tag_options(["foo"])
        assert selection_is_empty([], spec)

    def test_non_empty_spec_with_results(self) -> None:
        spec = parse_tag_options(["foo"])
        e = _make_entity("a", tags=["foo"])
        assert not selection_is_empty([e], spec)
