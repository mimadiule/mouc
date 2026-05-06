"""Tag-based entity selection and transitive closure for --tags filtering."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .models import Entity, FeatureMap


@dataclass(frozen=True)
class TagFilterSpec:
    """Parsed tag filter specification from CLI --tags options."""

    include: frozenset[str]
    exclude: frozenset[str]
    direction: Literal["both", "up", "down"]

    @property
    def is_empty(self) -> bool:
        """True iff include and exclude are both empty (spec selects all entities)."""
        return not self.include and not self.exclude


# TODO(unify-tag-tokenisation): comma-split-and-strip here duplicates _collect_style_tags
# (cli.py). Consider extracting a shared tokenisation helper if the rule ever changes.
def parse_tag_options(
    raw: list[str] | None,
    direction: Literal["both", "up", "down"] = "both",
) -> TagFilterSpec:
    """Parse --tags option values into a TagFilterSpec.

    Accepts repeated values and comma-separated within a single value.
    Strips whitespace from each token. ``!tag`` prefix means exclude.
    Empty/None input produces an empty spec (selects all).
    """
    include: set[str] = set()
    exclude: set[str] = set()

    if raw:
        for item in raw:
            for raw_token in item.split(","):
                stripped = raw_token.strip()
                if not stripped:
                    continue
                if stripped.startswith("!"):
                    remainder = stripped[1:].strip()
                    if not remainder:
                        raise ValueError(
                            f"Invalid --tags value {stripped!r}: '!' must be followed by a tag name"
                        )
                    exclude.add(remainder)
                else:
                    include.add(stripped)

    return TagFilterSpec(
        include=frozenset(include),
        exclude=frozenset(exclude),
        direction=direction,
    )


def select_entities(feature_map: FeatureMap, spec: TagFilterSpec) -> list[Entity]:
    """Return entities selected by spec, in feature_map.entities order.

    If spec.is_empty: returns all entities unchanged.
    Otherwise computes direct matches, transitive closure in the requested
    direction, sibling-phase expansion, then negation removal.
    """
    if spec.is_empty:
        return list(feature_map.entities)

    all_entities = feature_map.entities
    entity_by_id: dict[str, Entity] = {e.id: e for e in all_entities}

    # When no positive includes, start from all; otherwise find direct matches.
    if not spec.include:
        direct: set[str] = {e.id for e in all_entities}
    else:
        direct = {e.id for e in all_entities if set(e.tags) & spec.include}

    # TODO(unify-transitive-traversal): this BFS duplicates StylingContext.transitively_requires/
    # enables (styling.py) and GraphGenerator._find_all_dependencies (graph.py). Consider a shared
    # graph-walk utility; note StylingContext has a cache this implementation doesn't use.

    def _bfs_directed(seeds: set[str], use_up: bool, use_down: bool) -> set[str]:
        """BFS from seeds following only the specified directions; returns reachable IDs."""
        visited: set[str] = set(seeds)
        queue: deque[str] = deque(seeds)
        while queue:
            eid = queue.popleft()
            entity = entity_by_id.get(eid)
            assert entity is not None, f"BFS reached unknown entity ID {eid!r}"
            neighbors: set[str] = set()
            if use_up:
                neighbors |= entity.requires_ids
            if use_down:
                neighbors |= entity.enables_ids
            for nid in neighbors:
                if nid not in visited and nid in entity_by_id:
                    visited.add(nid)
                    queue.append(nid)
        return visited

    # For "both", compute upstream and downstream of direct independently and union them.
    # A single combined BFS would incorrectly walk upstream from downstream-reached entities.
    if spec.direction == "both":
        up_set = _bfs_directed(direct, use_up=True, use_down=False)
        down_set = _bfs_directed(direct, use_up=False, use_down=True)
        closure: set[str] = up_set | down_set
    else:
        closure = _bfs_directed(
            direct,
            use_up=spec.direction == "up",
            use_down=spec.direction == "down",
        )

    # Sibling-phase expansion (A2):
    # (a) any entity in closure that is a phase -> add all siblings (same phase_of[0])
    # (b) any entity in closure that is a parent of phases -> add all phase children
    phase_parents_in_closure = {
        e.phase_of[0]
        for e in all_entities
        if e.id in closure and e.phase_of and e.phase_of[0] in entity_by_id
    }
    sibling_parents = closure | phase_parents_in_closure
    siblings: set[str] = set()
    for e in all_entities:
        if e.phase_of and e.phase_of[0] in sibling_parents:
            siblings.add(e.id)
        if e.id in phase_parents_in_closure:
            siblings.add(e.id)

    final = (closure | siblings) - {e.id for e in all_entities if set(e.tags) & spec.exclude}

    return [e for e in all_entities if e.id in final]


def selection_is_empty(result: list[Entity], spec: TagFilterSpec) -> bool:
    """Return True iff a non-empty spec produced an empty result."""
    return not spec.is_empty and len(result) == 0
