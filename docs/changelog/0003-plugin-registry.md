# Engineering Changelog 0003: Module 1.3 Plugin Registry

- **Completed module:** Phase 1, Module 1.3
- **Status:** Complete
- **Recorded:** 2026-08-07
- **Specifications:** [ADR-0002: Core Interface Contracts](../adr/ADR-0002-core-interface-contracts.md), engineering roadmap Module 1.3
- **Previous module:** Phase 1, Module 1.2 — Core Interface Contracts
- **Next module:** Phase 1, Module 1.4 — Configuration System

## Summary

Module 1.3 introduces the transport-independent plugin infrastructure used to
register, validate, order, discover, and resolve implementations of the Phase 1
provider contracts. It ships no concrete plugins or provider behavior.

## Public API delivered

- `PluginRegistry` with deterministic typed registration and resolution for
  parser, chunker, embedding provider, retriever, reranker, LLM, and storage
  capability slots.
- `PluginInterfaceV1` and its current-version alias.
- Immutable `PluginDescriptor`, `RegistrationDescriptor`, and
  `PluginLoadResult` records.
- `CapabilityKind`, `PluginSource`, and `RegistryState` enums.
- Typed registry validation, discovery, compatibility, conflict, and frozen
  state exceptions.
- Built-in object loading, Python `mnemo.plugins` entry-point discovery, and
  explicit local module/package path discovery.

## Architectural decisions carried forward

- Registration is mutable only while a registry is open; `freeze()` makes its
  registration state immutable.
- Plugin compatibility uses semantic versions and declared core version
  ranges.
- Higher priority wins deterministically; distinct equal-priority candidates
  are explicit conflicts.
- One plugin registration is atomic. A failed plugin rolls back only its own
  registrations, and bulk discovery isolates candidates.
- Provider conformance is structural against the approved V1 protocols.
- Descriptor and extension metadata use immutable, namespaced values.
- `MNEMO_PLUGINS` remains a deprecated standalone Module 1.x compatibility
  path. KnowledgeEngine passes resolved configuration paths explicitly.

## Compatibility guarantees

- The plugin entry-point group is `mnemo.plugins`.
- The plugin contract version is `v1`.
- Registry slots and descriptors expose no transport or infrastructure-vendor
  types.
- Frozen registry inspection returns immutable deterministic metadata.

## Downstream impact

Module 1.5 owns and freezes one registry during composition. Later storage,
parser, chunker, embedding, retrieval, reranking, and LLM modules register
replaceable implementations without changing core consumers.
