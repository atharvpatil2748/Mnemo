"""Validate WP-16 manifests or score a protected external-client transcript."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
from mnemo_server.evaluation import (
    BehavioralTranscript,
    BlindAgentEvaluator,
    load_behavioral_manifest,
    redact_transcript,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--scenario-id")
    parser.add_argument("--transcript", type=Path)
    return parser


def main() -> int:
    """Validate inputs and print only a redacted deterministic verdict."""
    args = _parser().parse_args()
    raw_manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.schema is not None:
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        jsonschema.validate(raw_manifest, schema)
    manifest = load_behavioral_manifest(args.manifest)
    if args.transcript is None:
        print(
            json.dumps(
                {
                    "schema_version": manifest.schema_version,
                    "corpus_id": manifest.corpus_id,
                    "scenario_count": len(manifest.scenarios),
                    "scenario_ids": [item.scenario_id for item in manifest.scenarios],
                },
                sort_keys=True,
            )
        )
        return 0
    if args.scenario_id is None:
        raise SystemExit("--scenario-id is required with --transcript")
    scenarios = {item.scenario_id: item for item in manifest.scenarios}
    if args.scenario_id not in scenarios:
        raise SystemExit("unknown scenario ID")
    transcript = BehavioralTranscript.model_validate_json(
        args.transcript.read_text(encoding="utf-8")
    )
    if transcript.scenario_id != args.scenario_id:
        raise SystemExit("transcript scenario does not match --scenario-id")
    verdict = BlindAgentEvaluator().evaluate(scenarios[args.scenario_id], transcript)
    print(
        json.dumps(
            {
                "transcript": redact_transcript(transcript),
                "verdict": verdict.model_dump(mode="json"),
            },
            sort_keys=True,
        )
    )
    return 0 if verdict.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
