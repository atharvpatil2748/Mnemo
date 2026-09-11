# Phase 8.5 WP-15 Model Profile Runbook

## Authority and precedence

`mnemo.toml` selects one tracked profile document and profile name:

```toml
[phase85]
profile_file = "./config/model_profiles/phase8_5_profiles.toml"
profile_name = "phase8_5_local_v1"
```

The deterministic precedence is, from highest to lowest:

1. environment leaf override;
2. inline `[models.<component>]` value;
3. selected profile-document value;
4. unchanged V1 defaults for V1 services.

There is no implicit provider or cloud fallback. An invalid file, unknown
profile, incomplete enabled component, or unsupported profile document fails
configuration loading.

## Selecting an operating mode

- Normal Phase 8.5 candidate: `MNEMO_PHASE85_PROFILE_NAME=phase8_5_local_v1`
- V1 only: `MNEMO_PHASE85_PROFILE_NAME=v1_only`
- All Phase 8.5 features disabled: `MNEMO_PHASE85_PROFILE_NAME=disabled`

The reduced profiles do not alter `[embedding]`, `[reranker]`, or V1 LLM role
configuration. V1 startup therefore remains independent of optional V2 models.

## Operator-owned model paths

Set `MNEMO_PHASE85_MODEL_ROOT` (or `[phase85].model_root`) when providers need a
local model cache. The resolved path is private operator state. It is excluded
from profile fingerprints exposed to clients, capability documents, and logs.
No personal drive path belongs in a tracked profile.

## Generation activation

The runtime computes one SHA-256 fingerprint from the resolved, immutable,
secret-free profile snapshot. A generation-backed capability is READY/ACTIVE
only when its active generation is bound to that exact fingerprint and all
existing integrity/coverage checks pass. After any material provider, model,
revision, dimension, preprocessing, or capability override:

1. start the runtime and inspect `GET /v2/capabilities` or MCP
   `get_capabilities` for the new redacted fingerprint;
2. build a new immutable projection generation using that fingerprint;
3. validate integrity and coverage;
4. atomically activate the new generation;
5. confirm capability readiness again.

Never relabel an old generation with a new fingerprint.

## Rollback

Select the previous tracked profile and atomically restore its matching READY
generation aliases. If the Phase 8.5 dependencies cannot be restored, select
`v1_only`. This leaves frozen V1 provider configuration and behavior unchanged.

## Public diagnostics

Capability discovery exposes profile ID, version, mode, trust class,
certification label, fingerprint, component provider/model/revision/dimensions,
and readiness. It intentionally omits model roots, profile-file paths,
credentials, environment values, and signing material. `candidate` and
`non_certified_default` are not certification claims.
