# 0080 — WP-11 deterministic multi-document retrieval

Added an additive partitioned retrieval primitive over the existing advanced
retrieval service. Explicit document partitions execute deterministically and
retain per-document provenance, completeness, snapshots, and CursorCodecV2
continuations. Existing V1 and structured semantics are unchanged.
