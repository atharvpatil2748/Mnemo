# Engineering Changelog 0004: Module 1.4 Configuration System

- **Completed module:** Phase 1, Module 1.4
- **Status:** Complete
- **Recorded:** 2026-08-07
- **Specification:** [ADR-0003: Configuration System](../adr/ADR-0003-configuration-system.md)
- **Previous module:** Phase 1, Module 1.3 — Plugin Registry System
- **Next module:** Phase 1, Module 1.5 — KnowledgeEngine Entrypoint

## Summary

Module 1.4 establishes the single typed configuration authority for Mnemo.
It loads the canonical TOML format, applies explicit environment overrides,
validates the resolved values, prepares configured local directories, and
returns an immutable runtime snapshot. It performs no provider selection,
storage initialization, registry injection, or network access.

## Public API delivered

- `MnemoConfig` as the frozen root snapshot.
- `StorageConfig` with explicit filesystem, SQLite, Qdrant, and SurrealDB
  backend sections.
- `LLMConfig` and `LLMRoleConfig` for the mandatory planner, synthesizer,
  extractor, and classifier roles.
- `EmbeddingConfig`, `RerankerConfig`, and `PluginConfig` as separate provider
  families.
- Backend-specific configuration records containing only the V1 fields frozen
  by ADR-0003.
- `MnemoConfig.from_file()` for TOML plus environment loading and
  `MnemoConfig.from_env()` for environment-only loading.
- Standard Pydantic `model_dump()`, JSON-mode dumping, and `model_dump_json()`
  serialization.

## Architectural decisions carried forward

- V1 has exactly five root sections: storage, LLM, embedding, reranker, and
  plugins. Later roadmap namespaces remain reserved and unimplemented.
- Provider and model names are required free-form identifiers; availability is
  validated by later registry composition rather than configuration parsing.
- Composite storage is the set of explicitly enabled nested backends and has no
  backend-selector field.
- Configuration precedence is defaults, TOML, environment, validation, then a
  frozen snapshot.
- Unknown TOML keys fail validation while unknown environment variables are
  ignored.
- Relative TOML paths resolve against the file location; environment-only paths
  resolve against the current working directory.
- `MNEMO_PLUGINS_DIRECTORY` is canonical. `MNEMO_PLUGINS` remains a deprecated
  loading alias for Module 1.x compatibility.
- Module 1.3 remains unchanged. Module 1.5 is the designated first integration
  point for injecting resolved plugin configuration.

## Compatibility guarantees

- Existing V1 field names, meanings, defaults, environment names, precedence,
  and path bases are stable public behavior.
- Future configuration evolves additively during its assigned roadmap phases.
- Frozen snapshots are replaced as a whole by any future reload mechanism and
  are never mutated in place.
- TOML is the only V1 configuration-file format; YAML, JSON, and dotenv files
  are not accepted configuration sources.

## Downstream impact

Module 1.5 can construct the engine, registry, providers, and storage adapters
from one validated snapshot. Phase 2 storage implementations consume their
backend sections without reading process or file configuration. Later LLM,
embedding, reranking, and plugin modules receive their respective typed
sections through dependency injection.
