# ADR-0005: Graph Identity Resolution

- **Status:** Proposed
- **Date:** 2026-08-08
- **Decision owners:** Mnemo maintainers
- **Scope:** Phase 2, Module 2.4 (Graph persistence)
- **Supersedes:** ADR-0001 and ADR-0002 (Graph identity only)
- **Related documents:** `mnemo_architecture_v2.md`, `ADR-0001-domain-model-specification.md`, `ADR-0002-core-interface-contracts.md`

## 1. Context

During the implementation of Phase 2, Module 2.4 (SurrealDB Graph Store), a major schema ambiguity was discovered between the domain models defined in ADR-0001 and the `StorageInterfaceV1` contract defined in ADR-0002.

- `Entity` was defined in ADR-0001 as an immutable value object without a unique ID, storing a `name: str`.
- `GraphEdge` was defined in ADR-0001 to link entities using `source: str` and `target: str` (their normalized names).
- `StorageInterfaceV1` defined `get_entity(self, entity_id: UUID)` and `get_related_entities(self, entity_id: UUID)`, contradicting the lack of UUIDs in the graph domain models.

Relying on names as graph identities couples entity identity to entity naming, complicating future entity deduplication, graph merging, cross-document reasoning, and notebook linking.

## 2. Decision

We will separate entity identity from entity naming. The `Entity` model shall become an aggregate root rather than a pure value object.

Specifically:
1. **Stable UUID:** Every `Entity` receives a stable UUID (`entity_id`).
2. **Canonical Name:** The `name` field is renamed to `canonical_name` to clarify its role.
3. **Immutable Aliases:** Aliases remain immutable alternate names for the canonical entity.
4. **UUID Edges:** `GraphEdge` shall reference entities exclusively by their UUIDs (`source_id: UUID` and `target_id: UUID`), rather than by names.
5. **No Name-based Identity:** Entity names are never used as graph identity. Entity resolution will later map extracted names onto existing UUID-backed entities.

## 3. Consequences

- **Positive:** Mnemo is prepared for cross-document entity deduplication, merging, and more advanced graph traversals.
- **Positive:** The public interface `StorageInterfaceV1` becomes internally consistent and logically sound.
- **Negative:** `ADR-0001` and `ADR-0002` require updates to reflect the new structure.

## 4. Required Schema Updates

### 4.1 Entity (Updates ADR-0001, Section 9.1)
```python
class Entity:
    entity_id: UUID
    canonical_name: str
    type: str
    confidence: float
    document_id: UUID
    aliases: tuple[str, ...] = ()
```

### 4.2 GraphEdge (Updates ADR-0001, Section 9.2)
```python
class GraphEdge:
    source_id: UUID
    target_id: UUID
    relation: str
    weight: float
```

### 4.3 StorageInterfaceV1 (Updates ADR-0002)
- `upsert_entity(self, entity: Entity) -> None`
- `upsert_edge(self, edge: GraphEdge) -> None`
- `get_entity(self, entity_id: UUID) -> Entity | None`
- `find_entities(self, normalized_name: str, entity_type: str | None, document_ids: tuple[UUID, ...], limit: int) -> tuple[Entity, ...]`
- `get_related_entities(self, entity_id: UUID, hops: int, relations: tuple[str, ...], limit: int) -> tuple[Entity, ...]`
- `delete_graph_for_document(self, document_id: UUID) -> None`
