"""Owner-run, resumable four-notebook *disposable* Phase 8.6 experiment.

The existing notebook is copied from its verified recovery snapshot. Its source
association is never rewritten. New language notebooks reuse identical indexed
documents through the governed source-association service; no prior OCR/Vision/
CLIP inference is falsely reported as new inference.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import msvcrt
import os
import shutil
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

ROOT = Path(__file__).resolve().parents[1]
if TYPE_CHECKING:
    from mnemo.config import MnemoConfig
    from mnemo.interfaces import StorageInterfaceV1
    from mnemo.models import Notebook
    from mnemo_server.services.ingestion import IngestionService
    from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PLAN = ROOT / "config/evaluation/phase86_four_notebooks.v1.json"
CORPUS = ROOT / "evaluationDataset/Phase 8.6 Format-Diverse Multilingual Evaluation Corpus"
MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
CACHE = Path("D:/Mnemo/phase8.5.11-models/huggingface/hub")
CAPABILITIES = (
    "representation_derivation_v2",
    "language_text_v2",
    "multilingual_embedding_v2",
    "multilingual_vector_v2",
)
REVIEWED_PARTITION_SHA256 = "96a2c0ca3a73de299e90d0de688b475719bea7b1f32658e9d7a547ce31090d46"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def publication_state(logs: Path, filename: str, **fields: object) -> None:
    """Durably record a resumable per-file state; SQL remains authoritative."""
    path = logs / "publication_states.json"
    states: dict[str, Any] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    states[filename] = {**states.get(filename, {}), **fields}
    write_json(path, states)


def commit_pre_activation_audit(logs: Path, result: dict[str, object]) -> str:
    """Freeze the passing audit before any alias write; never replace its receipt."""
    if result.get("status") != "PASS":
        raise RuntimeError("independent pre-activation audit failed")
    value = {
        **result,
        "provider_results_sha256": digest(logs / "provider_results.json"),
        "phase": "PRE_ACTIVATION",
    }
    path = logs / "pre_activation_audit.json"
    serialized = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != serialized:
            raise RuntimeError("previous pre-activation audit receipt differs")
    else:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
    return digest(path)


def notebook_ids(plan: dict[str, Any]) -> dict[str, UUID]:
    key = str(plan["run_key"])
    return {
        language: uuid5(NAMESPACE_URL, f"mnemo:{key}:{language}") for language in ("hi", "mr", "en")
    }


def planned_notebook(plan: dict[str, Any], language: str, notebook_id: UUID) -> Notebook:
    from mnemo.models import FrozenMetadata, Notebook

    now = datetime.fromisoformat(str(plan["created_at"]))
    return Notebook(
        notebook_id=notebook_id,
        title=str(plan["notebooks"][language]["title"]),
        description="Disposable language-specific Phase 8.6 evaluation",
        created_at=now,
        updated_at=now,
        metadata=FrozenMetadata({"language": language}),
    )


def same_notebook(left: Notebook, right: Notebook) -> bool:
    return (
        left.notebook_id,
        left.title,
        left.description,
        left.created_at,
        left.updated_at,
        left.metadata,
    ) == (
        right.notebook_id,
        right.title,
        right.description,
        right.created_at,
        right.updated_at,
        right.metadata,
    )


def isolated_config(runtime: Path) -> MnemoConfig:
    from mnemo.config import MnemoConfig

    os.environ["MNEMO_STORAGE_SQLITE_PATH"] = str(runtime / "mnemo.db")
    os.environ["MNEMO_STORAGE_FILESYSTEM_ROOT"] = str(runtime / "files")
    os.environ["MNEMO_STORAGE_SQLITE_ENABLED"] = "true"
    os.environ["MNEMO_STORAGE_FILESYSTEM_ENABLED"] = "true"
    os.environ["MNEMO_STORAGE_QDRANT_ENABLED"] = "false"
    os.environ["MNEMO_STORAGE_SURREALDB_ENABLED"] = "false"
    config = MnemoConfig.from_file(ROOT / "mnemo.toml")
    if (
        config.storage.sqlite.path.resolve() != (runtime / "mnemo.db").resolve()
        or config.storage.filesystem.root.resolve() != (runtime / "files").resolve()
        or config.storage.qdrant.enabled
        or config.storage.surrealdb.enabled
    ):
        raise RuntimeError("isolated storage configuration differs from the disposable run")
    return config


def run_paths(plan: dict[str, Any]) -> tuple[str, Path, Path]:
    identity = hashlib.sha256(PLAN.read_bytes()).hexdigest()[:16]
    run_id = f"{plan['run_key']}-{identity}"
    return (
        run_id,
        ROOT / "scratch/module_894_four_notebooks" / run_id,
        ROOT / "logs/evaluation_ingestion" / run_id,
    )


def verify_output_boundary(runtime: Path, logs: Path) -> None:
    for path, base in (
        (runtime, ROOT / "scratch/module_894_four_notebooks"),
        (logs, ROOT / "logs/evaluation_ingestion"),
    ):
        if base.is_symlink() or path.is_symlink():
            raise RuntimeError("disposable output path is a symbolic link")
        if not base.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError("disposable output base escaped workspace")
        if path.parent != base or path.resolve().parent != base.resolve():
            raise RuntimeError("disposable output path escaped its run directory")


def preflight() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if Path.cwd().resolve() != ROOT.resolve() or not (ROOT / "mnemo.toml").is_file():
        raise RuntimeError("run from the Mnemo repository root")
    if (
        json.loads((ROOT / "config/production/runtime-selection.json").read_text())["state"]
        != "UNINDEXED"
    ):
        raise RuntimeError("production selector is not UNINDEXED")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if plan.get("schema") != "mnemo.phase86-four-notebook-plan/1" or tuple(plan["notebooks"]) != (
        "hi",
        "mr",
        "en",
    ):
        raise RuntimeError("unexpected evaluation plan")
    source_manifest = ROOT / str(plan["source_manifest"])
    if digest(source_manifest) != plan["source_manifest_sha256"]:
        raise RuntimeError("source inventory manifest changed")
    inventory = json.loads(source_manifest.read_text(encoding="utf-8"))
    records = {item["relative_path"]: item for item in inventory["sources"]}
    if len(records) != 24 or len(inventory["sources"]) != 24:
        raise RuntimeError("source manifest count changed")
    for name, item in records.items():
        source = (CORPUS / name).resolve(strict=True)
        if source.parent != CORPUS.resolve() or source.is_symlink():
            raise RuntimeError(f"source path escaped corpus: {name}")
        if source.stat().st_size != item["byte_size"] or digest(source) != item["sha256"]:
            raise RuntimeError(f"source bytes changed: {name}")
    assigned = [name for spec in plan["notebooks"].values() for name in spec["files"]]
    if (
        len(assigned) != 20
        or len(set(assigned)) != 20
        or any(name not in records for name in assigned)
    ):
        raise RuntimeError("three-notebook assignment is not the reviewed 20-file partition")
    partition = {key: sorted(value["files"]) for key, value in plan["notebooks"].items()}
    partition_digest = hashlib.sha256(
        json.dumps(partition, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if partition_digest != REVIEWED_PARTITION_SHA256:
        raise RuntimeError("language assignment differs from the reviewed partition")
    excluded = "dcfa97c8-e6e7-41d3-95d1-88dacb65e492.pdf"
    if excluded in assigned or any(name.startswith("PHASE8_6_") for name in assigned):
        raise RuntimeError("rejected PDF or governance report entered the new partition")
    old = plan["existing_notebook"]
    snapshot, retired, files = (
        ROOT / old[field] for field in ("snapshot", "retired_store", "retained_files")
    )
    if digest(snapshot) != old["snapshot_sha256"] or digest(retired) != old["retired_store_sha256"]:
        raise RuntimeError("retired database or recovery snapshot differs from its receipt")
    if not files.is_dir() or not any(files.rglob("*.ir.json")):
        raise RuntimeError("retained parsed files are unavailable")
    with sqlite3.connect(
        f"file:{snapshot.resolve().as_posix()}?mode=ro&immutable=1", uri=True
    ) as db:
        row = db.execute("SELECT title FROM notebooks WHERE notebook_id=?", (old["id"],)).fetchone()
        count = db.execute(
            "SELECT COUNT(*) FROM sources WHERE notebook_id=?", (old["id"],)
        ).fetchone()[0]
        if row != (old["title"],) or count != 24:
            raise RuntimeError("snapshot does not contain the identified 24-source notebook")
        retained_hashes = {
            value[0]
            for value in db.execute(
                "SELECT d.current_hash FROM sources s JOIN documents d "
                "ON d.document_id=s.document_id WHERE s.notebook_id=?",
                (old["id"],),
            )
        }
        if retained_hashes != {item["sha256"] for item in records.values()}:
            raise RuntimeError("historical source membership differs from the 24-file inventory")
        for name in assigned:
            source = records[name]
            present = db.execute(
                "SELECT current_version_id FROM documents "
                "WHERE current_hash=? AND status='indexed'",
                (source["sha256"],),
            ).fetchone()
            if present is None:
                raise RuntimeError(f"existing indexed document missing: {name}")
            version_id = str(present[0])
            parsed = files / "parsed" / version_id[:8] / f"{version_id}.ir.json"
            if not parsed.is_file():
                raise RuntimeError(f"persisted parsed representation missing: {name}")
            if not isinstance(json.loads(parsed.read_text(encoding="utf-8")).get("blocks"), list):
                raise RuntimeError(f"persisted parsed representation is malformed: {name}")
    if not (CACHE / "models--BAAI--bge-m3/snapshots" / MODEL_REVISION).is_dir():
        raise RuntimeError("verified local BGE-M3 revision is unavailable")
    from scripts.phase86_identity_qrels import load_blueprint

    load_blueprint(plan, records)
    return plan, records


class Log:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path, self.run_id = path, run_id

    def emit(self, stage: str, message: str, **fields: object) -> None:
        value = {
            "at": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "stage": stage,
            "message": message,
            **fields,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        print(f"[{self.run_id}] {stage}: {message}", flush=True)


def archive_quarantined_attempt(logs: Path) -> Path | None:
    """Preserve a failed attempt's receipts before a same-run retry updates them."""
    state = logs / "run_state.json"
    if (
        not state.is_file()
        or json.loads(state.read_text(encoding="utf-8")).get("status") != "QUARANTINED"
    ):
        return None
    files = sorted(path for path in logs.iterdir() if path.is_file() and path.name != "run.lock")
    if not files:
        raise RuntimeError("quarantined run has no receipts to preserve")
    attempts = logs / "attempts"
    attempts.mkdir(exist_ok=True)
    number = 1
    while (attempts / f"attempt-{number:03d}").exists() or (
        attempts / f".attempt-{number:03d}.copying"
    ).exists():
        number += 1
    destination = attempts / f"attempt-{number:03d}"
    temporary = attempts / f".attempt-{number:03d}.copying"
    temporary.mkdir()
    receipts: dict[str, str] = {}
    for path in files:
        target = temporary / path.name
        shutil.copy2(path, target)
        expected = digest(path)
        if digest(target) != expected:
            raise RuntimeError(f"failed to preserve quarantined receipt: {path.name}")
        receipts[path.name] = expected
    write_json(temporary / "archive_manifest.json", receipts)
    os.replace(temporary, destination)
    return destination


@contextmanager
def exclusive_run(lock_path: Path) -> Iterator[None]:
    """An OS-released, per-run Windows lock; a crashed process cannot strand it."""
    with lock_path.open("a+b") as stream:
        try:
            stream.seek(0)
            if not stream.read(1):
                stream.seek(0)
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("another process owns the disposable ingestion run") from error
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def prepare_copy(plan: dict[str, Any], runtime: Path, log: Log) -> None:
    old = plan["existing_notebook"]
    snapshot, retained = ROOT / old["snapshot"], ROOT / old["retained_files"]
    database = runtime / "mnemo.db"
    if not database.exists():
        temporary = runtime / "mnemo.db.copying"
        shutil.copy2(snapshot, temporary)
        if digest(temporary) != old["snapshot_sha256"]:
            raise RuntimeError("snapshot copy failed digest validation")
        os.replace(temporary, database)
        log.emit("snapshot", "verified historical notebook copied into isolated run")
    files = runtime / "files"
    for source in sorted(path for path in retained.rglob("*") if path.is_file()):
        relative = source.relative_to(retained)
        destination = files / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected = digest(source)
        if destination.exists():
            if digest(destination) != expected:
                raise RuntimeError(f"retained asset copy differs: {relative}")
            continue
        temporary = destination.with_name(destination.name + ".copying")
        shutil.copy2(source, temporary)
        if digest(temporary) != expected:
            raise RuntimeError(f"retained asset copy failed: {relative}")
        os.replace(temporary, destination)
    log.emit(
        "snapshot",
        "retained parsed/original/asset files verified",
        files=sum(1 for path in retained.rglob("*") if path.is_file()),
    )


async def create_notebooks(
    plan: dict[str, Any], database: Path, authority: SQLiteNotebookScopeAuthority, log: Log
) -> None:
    from mnemo.storage.sqlite import SQLiteStore
    from mnemo_server.services.membership_lifecycle import MembershipNotebookLifecycle

    actor = UUID(str(plan["disposable_actor_id"]))
    old_id = UUID(str(plan["existing_notebook"]["id"]))
    store = SQLiteStore(database)
    await store.open()
    try:
        original = await store.get_notebook(old_id)
        if original is None:
            raise RuntimeError("historical notebook vanished from disposable copy")
        if authority.active_role(actor, old_id) is None:
            if authority.revision(old_id) is not None:
                raise RuntimeError("disposable historical notebook owner was revoked")
            authority.grant(actor_id=actor, notebook_id=old_id, role="owner", operator_id=actor)
        elif authority.active_role(actor, old_id) != "owner":
            raise RuntimeError("historical notebook has conflicting disposable ACL")
        lifecycle = MembershipNotebookLifecycle(store, authority)
        for language, notebook_id in notebook_ids(plan).items():
            expected = planned_notebook(plan, language, notebook_id)
            token = uuid5(NAMESPACE_URL, f"{plan['run_key']}:{language}:creation")
            creation = (actor, token)
            existing = await store.get_notebook(notebook_id)
            if existing is not None:
                if not same_notebook(existing, expected):
                    raise RuntimeError(f"conflicting notebook state: {language}")
                if authority.active_role(actor, notebook_id) != "owner":
                    if authority.pending_create(notebook_id) != creation:
                        raise RuntimeError(
                            f"unowned notebook has no recoverable intent: {language}"
                        )
                    await lifecycle.recover_pending_create(notebook_id, actor)
                    log.emit("notebook", f"recovered interrupted create: {language}: {notebook_id}")
                else:
                    if authority.completed_create(notebook_id) != creation:
                        raise RuntimeError(f"notebook creation completion differs: {language}")
                    log.emit("notebook", f"resumed {language}: {notebook_id}")
                continue
            notebook = expected
            if authority.pending_create(notebook_id) is None:
                authority.reserve_create(
                    notebook_id=notebook_id, actor_id=actor, token=token, notebook=notebook
                )
            created = await lifecycle.recover_pending_create(notebook_id, actor)
            if created.notebook_id != notebook_id:
                raise RuntimeError("recovered notebook identity differs")
            log.emit("notebook", f"created {language}: {notebook_id}")
    finally:
        await store.close()


async def reconcile_known_failed_sources(
    plan: dict[str, Any],
    records: dict[str, dict[str, Any]],
    storage: StorageInterfaceV1,
    authority: SQLiteNotebookScopeAuthority,
    service: IngestionService,
    logs: Path,
    log: Log,
) -> None:
    """Recover only frozen-plan failed intents before ordinary ACL reads resume."""
    actor = UUID(str(plan["disposable_actor_id"]))
    configured = {notebook_id: language for language, notebook_id in notebook_ids(plan).items()}
    candidates = authority.unresolved_source_ingestion_intents()
    validated: list[tuple[UUID, str, str]] = []
    # Reject the entire census before changing any intent. A failed intent on
    # an unexpected notebook or source cannot be silently ignored.
    for notebook_id, intent_actor, content_hash, state in candidates:
        language = configured.get(notebook_id)
        if language is None or intent_actor != actor or state != "failed":
            raise RuntimeError("unrecognized source recovery intent")
        filenames = [
            filename
            for filename in plan["notebooks"][language]["files"]
            if records[filename]["sha256"] == content_hash
        ]
        if len(filenames) != 1:
            raise RuntimeError("source recovery hash is outside the frozen partition")
        expected = planned_notebook(plan, language, notebook_id)
        actual = await storage.get_notebook(notebook_id)
        token = uuid5(NAMESPACE_URL, f"{plan['run_key']}:{language}:creation")
        if (
            actual is None
            or not same_notebook(actual, expected)
            or authority.pending_create(notebook_id) is not None
            or authority.completed_create(notebook_id) != (actor, token)
            or not authority.source_ingestion_document_preexisted(
                actor_id=actor, notebook_id=notebook_id, content_hash=content_hash
            )
        ):
            raise RuntimeError("source recovery notebook ownership evidence differs")
        document = await storage.get_document_by_content_hash(content_hash)
        if (
            document is None
            or document.current_hash != content_hash
            or document.status.value != "indexed"
        ):
            raise RuntimeError("source recovery document identity differs")
        validated.append((notebook_id, content_hash, filenames[0]))
    for notebook_id, content_hash, filename in validated:
        log.emit("recovery", f"reconciling failed source intent: {filename}")
        await service.reconcile_failed_source_ingestion(
            notebook_id=notebook_id, content_hash=content_hash
        )
        if authority.source_ingestion_state(notebook_id, content_hash) != "recoverable":
            raise RuntimeError("source recovery intent did not become recoverable")
        receipt = logs / "source_recovery_receipts.json"
        entries: list[dict[str, str]] = (
            json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else []
        )
        entries.append(
            {
                "at": datetime.now(UTC).isoformat(),
                "actor_id": str(actor),
                "notebook_id": str(notebook_id),
                "filename": filename,
                "content_hash": content_hash,
                "prior_state": "failed",
                "reconciled_state": "recoverable",
            }
        )
        write_json(receipt, entries)
        log.emit("recovery", f"failed source intent reconciled: {filename}")
    for notebook_id, _, _ in validated:
        if authority.active_role(actor, notebook_id) != "owner" or not authority.permits(
            actor, notebook_id, operation="write"
        ):
            raise RuntimeError("ordinary owner authorization did not recover")


async def recover_before_notebook_resume(
    plan: dict[str, Any],
    records: dict[str, dict[str, Any]],
    runtime: Path,
    logs: Path,
    authority: SQLiteNotebookScopeAuthority,
    log: Log,
) -> None:
    if not authority.unresolved_source_ingestion_intents():
        return
    from mnemo.engine import KnowledgeEngine
    from mnemo.interfaces import PrincipalContextV1
    from mnemo.tokenizers import O200KBaseTokenCounter
    from mnemo_server.services.ingestion import IngestionService
    from mnemo_server.tokenizer_provisioning import provision_tokenizer

    engine = KnowledgeEngine(isolated_config(runtime))
    await engine.initialize()
    try:
        cast(Any, engine).server_scope_authority = authority
        service = IngestionService(
            engine,
            O200KBaseTokenCounter(provision_tokenizer()),
            principal=PrincipalContextV1(UUID(str(plan["disposable_actor_id"])), True),
        )
        await reconcile_known_failed_sources(
            plan, records, engine.storage, authority, service, logs, log
        )
    finally:
        await engine.shutdown()


async def link_sources(
    plan: dict[str, Any],
    records: dict[str, dict[str, Any]],
    runtime: Path,
    logs: Path,
    log: Log,
) -> None:
    from mnemo.engine import KnowledgeEngine
    from mnemo.interfaces import PrincipalContextV1
    from mnemo.tokenizers import O200KBaseTokenCounter
    from mnemo_server.services.ingestion import IngestionService
    from mnemo_server.tokenizer_provisioning import provision_tokenizer

    from scripts.audit_phase86_four_notebooks import validate_reused_document

    engine = KnowledgeEngine(isolated_config(runtime))
    await engine.initialize()
    try:
        from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority

        authority = SQLiteNotebookScopeAuthority(runtime / "acl.db")
        # This server-owned seam is intentionally not part of mnemo-core's engine type.
        cast(Any, engine).server_scope_authority = authority
        actor = UUID(str(plan["disposable_actor_id"]))
        service = IngestionService(
            engine,
            O200KBaseTokenCounter(provision_tokenizer()),
            principal=PrincipalContextV1(actor, True),
        )
        results: list[dict[str, object]] = []
        for language, notebook_id in notebook_ids(plan).items():
            for filename in plan["notebooks"][language]["files"]:
                if not authority.permits(actor, notebook_id, operation="write"):
                    raise PermissionError("disposable owner authorization changed during ingestion")
                source = records[filename]
                content_hash = str(source["sha256"])
                state_file = logs / "publication_states.json"
                prior_states = (
                    json.loads(state_file.read_text(encoding="utf-8"))
                    if state_file.exists()
                    else {}
                )
                previous_state = prior_states.get(filename, {}).get("state")
                if previous_state == "PUBLISHING":
                    publication_state(logs, filename, state="INTERRUPTED")
                publication_state(
                    logs,
                    filename,
                    state="DISCOVERED",
                    notebook_id=str(notebook_id),
                    sha256=content_hash,
                )
                log.emit(
                    "file",
                    f"{language}: {filename} ({Path(filename).suffix}; existing indexed content)",
                )
                state = authority.source_ingestion_state(notebook_id, content_hash)
                if state in {"incomplete", "failed", "quarantined", "recoverable"}:
                    await service.reconcile_failed_source_ingestion(
                        notebook_id=notebook_id, content_hash=content_hash
                    )
                snapshot_uri = (
                    "file:"
                    + (ROOT / plan["existing_notebook"]["snapshot"]).resolve().as_posix()
                    + "?mode=ro&immutable=1"
                )
                with (
                    closing(
                        sqlite3.connect(
                            snapshot_uri,
                            uri=True,
                        )
                    ) as original,
                    closing(
                        sqlite3.connect(
                            f"file:{(runtime / 'mnemo.db').resolve().as_posix()}?mode=ro", uri=True
                        )
                    ) as current,
                ):
                    validation = validate_reused_document(
                        original,
                        current,
                        content_hash=content_hash,
                        parsed_root=runtime / "files",
                        model_revision=MODEL_REVISION,
                    )
                if validation["status"] != "PASS":
                    publication_state(
                        logs, filename, state="VALIDATION_FAILED", errors=validation["errors"]
                    )
                    raise RuntimeError(
                        f"reused document validation failed: {filename}: {validation['errors']}"
                    )
                publication_state(
                    logs,
                    filename,
                    state="VALIDATED",
                    document_id=validation["document_id"],
                    version_id=validation["version_id"],
                    chunk_count=validation["chunk_count"],
                )
                document = await engine.storage.get_document_by_content_hash(content_hash)
                if document is None or document.status.value != "indexed":
                    raise RuntimeError(f"indexed source disappeared: {filename}")
                existing = await service._find_source_in_notebook(notebook_id, document.document_id)
                if previous_state == "PUBLISHED" and existing is None:
                    publication_state(
                        logs,
                        filename,
                        state="PUBLICATION_FAILED",
                        error_type="MissingPublishedSource",
                    )
                    raise RuntimeError(f"previously published source vanished: {filename}")
                if existing is None:
                    source_bytes = (CORPUS / filename).read_bytes()
                    if (
                        len(source_bytes) != source["byte_size"]
                        or hashlib.sha256(source_bytes).hexdigest() != content_hash
                    ):
                        publication_state(
                            logs,
                            filename,
                            state="VALIDATION_FAILED",
                            errors=["source bytes changed after preflight"],
                        )
                        raise RuntimeError(f"source bytes changed before publication: {filename}")
                    publication_state(logs, filename, state="PUBLISHING")
                    try:
                        response = await service.ingest_source(
                            notebook_id=notebook_id,
                            filename=filename,
                            data=source_bytes,
                        )
                        source_id = response.source_id
                    except BaseException as error:
                        publication_state(
                            logs,
                            filename,
                            state="PUBLICATION_FAILED",
                            error_type=type(error).__name__,
                        )
                        raise
                    result = "REUSED_INDEXED_DOCUMENT_AND_CREATED_SOURCE"
                else:
                    source_id = existing.source_id
                    result = "VERIFIED_EXISTING_SOURCE_ASSOCIATION"
                with sqlite3.connect(
                    f"file:{(runtime / 'mnemo.db').as_posix()}?mode=ro", uri=True
                ) as db:
                    association = db.execute(
                        "SELECT s.source_id,d.document_id,d.current_version_id,d.current_hash "
                        "FROM sources s JOIN documents d ON d.document_id=s.document_id "
                        "WHERE s.notebook_id=? AND s.source_id=?",
                        (str(notebook_id), str(source_id)),
                    ).fetchone()
                    chunk_count = db.execute(
                        "SELECT COUNT(*) FROM chunks WHERE document_id=? AND version_id=?",
                        (str(document.document_id), str(document.current_version_id)),
                    ).fetchone()[0]
                if (
                    association
                    != (
                        str(source_id),
                        validation["document_id"],
                        validation["version_id"],
                        content_hash,
                    )
                    or chunk_count != validation["chunk_count"]
                ):
                    publication_state(
                        logs, filename, state="PUBLICATION_FAILED", error_type="AssociationMismatch"
                    )
                    raise RuntimeError(
                        f"published source association differs from validation: {filename}"
                    )
                publication_state(logs, filename, state="PUBLISHED", source_id=str(source_id))
                item = {
                    "language_partition": language,
                    "filename": filename,
                    "sha256": content_hash,
                    "notebook_id": str(notebook_id),
                    "source_id": str(source_id),
                    "document_id": str(document.document_id),
                    "version_id": str(document.current_version_id),
                    "chunk_count": chunk_count,
                    "result": result,
                    "parsing": "REUSED_PERSISTED",
                    "ocr_vision_clip": "REUSED_PERSISTED_WHERE_PRESENT",
                }
                results.append(item)
                write_json(logs / "file_results.json", results)
                log.emit("file", f"{language}: {filename}: {result}; chunks={chunk_count}")
        write_json(logs / "document_results.json", results)
    finally:
        await engine.shutdown()


def reconcile_legacy_schema(database: Path) -> None:
    with closing(sqlite3.connect(database)) as db, db:
        columns = {
            row[1] for row in db.execute("PRAGMA table_info(multilingual_coverage_manifests_v2)")
        }
        count = db.execute("SELECT COUNT(*) FROM multilingual_coverage_manifests_v2").fetchone()[0]
        if count and not {"capability", "item_identity_digest"}.issubset(columns):
            raise RuntimeError("cannot reconcile nonempty legacy generation manifests")
        for column in ("capability", "item_identity_digest"):
            if column not in columns:
                db.execute(
                    "ALTER TABLE multilingual_coverage_manifests_v2 "
                    f"ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )


def generation_membership_census(
    database: Path, notebook_ids: tuple[UUID, ...], *, immutable: bool
) -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Compare exact source/version ancestry in the WAL-aware and builder views."""
    suffix = "?mode=ro&immutable=1" if immutable else "?mode=ro"
    with closing(sqlite3.connect(database.resolve().as_uri() + suffix, uri=True)) as db:
        result: list[tuple[tuple[str, ...], ...]] = []
        for notebook_id in notebook_ids:
            rows = tuple(
                tuple("" if value is None else str(value) for value in row)
                for row in db.execute(
                    "SELECT s.notebook_id,s.source_id,s.document_id,"
                    "d.current_version_id,d.current_hash,d.status,"
                    "v.version_id,v.content_hash,v.status,"
                    "(SELECT COUNT(*) FROM chunks c WHERE c.document_id=s.document_id "
                    "AND c.version_id=v.version_id AND TRIM(c.text)<>'') "
                    "FROM sources s LEFT JOIN documents d ON d.document_id=s.document_id "
                    "LEFT JOIN document_versions v ON v.document_id=s.document_id "
                    "WHERE s.notebook_id=? ORDER BY s.source_id,v.version_id",
                    (str(notebook_id),),
                )
            )
            if not rows or any(
                row[0] != str(notebook_id)
                or not all(row[:9])
                or row[5] not in {"indexed", "enriched"}
                or (row[6] == row[3] and (row[8] != "current" or row[7] != row[4]))
                for row in rows
            ):
                raise RuntimeError(f"generation source census is ineligible: {notebook_id}")
            sources = {row[1] for row in rows}
            if any(
                not any(
                    row[1] == source_id and row[6] == row[3] and int(row[9]) > 0 for row in rows
                )
                for source_id in sources
            ):
                raise RuntimeError(
                    f"generation source census lacks current evidence: {notebook_id}"
                )
            result.append(rows)
        return tuple(result)


def checkpoint_and_verify_generation_input(
    database: Path, notebook_ids: tuple[UUID, ...]
) -> tuple[tuple[tuple[str, ...], ...], ...]:
    """Quiescent-run checkpoint before any immutable generation read or write."""
    if not database.is_file() or len(notebook_ids) != 4 or len(set(notebook_ids)) != 4:
        raise RuntimeError("generation checkpoint requires the four configured notebooks")
    try:
        with closing(sqlite3.connect(database, timeout=0, isolation_level=None)) as db:
            checkpoint = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    except sqlite3.Error as error:
        raise RuntimeError("generation WAL checkpoint failed") from error
    if (
        checkpoint is None
        or len(checkpoint) != 3
        or checkpoint[0] != 0
        or checkpoint[1] != checkpoint[2]
    ):
        raise RuntimeError(f"generation WAL checkpoint busy or incomplete: {checkpoint}")
    try:
        live = generation_membership_census(database, notebook_ids, immutable=False)
        frozen = generation_membership_census(database, notebook_ids, immutable=True)
    except sqlite3.Error as error:
        raise RuntimeError("generation source census failed") from error
    if live != frozen:
        raise RuntimeError("generation source census differs between live and immutable views")
    return live


def next_provider_attempt(database: Path, logs: Path) -> int:
    attempt_file = logs / "provider_attempt.json"
    previous = (
        json.loads(attempt_file.read_text(encoding="utf-8"))
        if attempt_file.exists()
        else {"attempt": 0, "failed_count_before": 0}
    )
    attempt = int(previous["attempt"])
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as db:
        failed = db.execute(
            "SELECT COUNT(*) FROM index_generations WHERE state='failed' "
            "AND capability IN (?,?,?,?)",
            CAPABILITIES,
        ).fetchone()[0]
    if failed > int(previous["failed_count_before"]):
        attempt += 1
    if attempt > 100:
        raise RuntimeError("isolated generation retry limit exceeded")
    write_json(attempt_file, {"attempt": attempt, "failed_count_before": failed})
    return attempt


async def build_generations(
    plan: dict[str, Any], runtime: Path, logs: Path, log: Log
) -> dict[str, Any]:
    from mnemo.phase85.isolated_multilingual import build_isolated_multilingual
    from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority

    database = runtime / "mnemo.db"
    reconcile_legacy_schema(database)
    authority = SQLiteNotebookScopeAuthority(runtime / "acl.db")
    actor = UUID(str(plan["disposable_actor_id"]))
    selected = (UUID(str(plan["existing_notebook"]["id"])), *notebook_ids(plan).values())

    def verify_owner() -> None:
        if any(
            not authority.permits(actor, identifier, operation="write") for identifier in selected
        ):
            raise PermissionError("disposable owner authority changed during projection build")

    def progress(completed: int, total: int) -> None:
        verify_owner()
        log.emit("embedding", f"persisted {completed}/{total} BGE-M3 evidence vectors")

    verify_owner()
    census = checkpoint_and_verify_generation_input(database, selected)
    verify_owner()
    log.emit(
        "provider",
        "checkpointed and verified immutable four-notebook generation input",
        sources=[len({row[1] for row in group}) for group in census],
    )
    build_file = logs / "provider_results.json"
    if build_file.exists():
        build = json.loads(build_file.read_text(encoding="utf-8"))
    else:
        attempt = next_provider_attempt(database, logs)
        log.emit(
            "provider",
            "building genuine BGE-M3 Full V2 projection for four authorized notebook memberships",
        )
        build = await build_isolated_multilingual(
            database=database,
            notebook_id=selected,
            profile_file=ROOT / "config/model_profiles/full_multilingual_v2_profiles.toml",
            cache_folder=CACHE,
            device="cuda",
            language_capability_file=ROOT / "config/rebuild/multilingual_embedding_capability.json",
            attempt=attempt,
            embedding_progress=progress,
        )
        if build["embedding_count"] != build["items"] or build["active"]:
            raise RuntimeError("BGE build did not produce complete READY projections")
        write_json(build_file, build)
    if set(build["notebook_ids"]) != {
        str(plan["existing_notebook"]["id"]),
        *(str(value) for value in notebook_ids(plan).values()),
    }:
        raise RuntimeError("BGE generation covers the wrong notebook selection")
    verify_owner()
    return cast(dict[str, Any], build)


async def promote_audited_alias(
    plan: dict[str, Any],
    runtime: Path,
    logs: Path,
    log: Log,
    build: dict[str, Any],
    audited_digest: str,
) -> None:
    from mnemo.phase85.v2_activation_authorization import first_v2_deactivation_recovery_digest
    from mnemo.storage.sqlite import SQLiteStore
    from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority

    audit_file = logs / "pre_activation_audit.json"
    if not audit_file.is_file() or digest(audit_file) != audited_digest:
        raise RuntimeError("immutable passing pre-activation audit receipt is missing or changed")
    manifest = json.loads((logs / "run_manifest.json").read_text(encoding="utf-8"))
    run_state = json.loads((logs / "run_state.json").read_text(encoding="utf-8"))
    if manifest.get("pre_activation_audit_sha256") != audited_digest or run_state != {
        "status": "PROMOTING",
        "pre_activation_audit_sha256": audited_digest,
    }:
        raise RuntimeError("run manifest does not authorize this audited promotion")
    audited = json.loads(audit_file.read_text(encoding="utf-8"))
    if audited.get("status") != "PASS" or audited.get("provider_results_sha256") != digest(
        logs / "provider_results.json"
    ):
        raise RuntimeError("pre-activation audit does not bind the current provider generation")
    actor = UUID(str(plan["disposable_actor_id"]))
    authority = SQLiteNotebookScopeAuthority(runtime / "acl.db")
    selected = (UUID(str(plan["existing_notebook"]["id"])), *notebook_ids(plan).values())
    if any(not authority.permits(actor, item, operation="write") for item in selected):
        raise PermissionError("disposable owner authority changed before alias promotion")
    authorization = {
        "scope": "isolated-disposable-evaluation-only",
        "run_key": plan["run_key"],
        "actor_id": str(actor),
        "notebook_ids": build["notebook_ids"],
        "generations": build["generations"],
        "profile_fingerprint": build["profile_fingerprint"],
    }
    authorization_digest = hashlib.sha256(
        json.dumps(authorization, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    store = SQLiteStore(runtime / "mnemo.db")
    await store.open()
    try:
        if await store.resolve_active_multilingual_v2_generation_set() is None:
            alias = await store.promote_multilingual_v2_alias_set(
                profile_fingerprint=build["profile_fingerprint"],
                generation_ids=tuple(UUID(build["generations"][key]) for key in CAPABILITIES),
                rollback_alias_set_digest=first_v2_deactivation_recovery_digest(
                    profile_fingerprint=build["profile_fingerprint"]
                ),
                rollback_generation_ids=(),
                expected_active_alias_set_digest=None,
                activation_mode="first_v2_activation",
                recovery_mode="deactivate_v2_alias_set",
                authorization_id=uuid5(NAMESPACE_URL, authorization_digest),
                authorization_digest=authorization_digest,
            )
            log.emit("provider", f"disposable Full V2 alias activated: {alias}")
        else:
            active = await store.resolve_active_multilingual_v2_generation_set()
            if active != tuple(UUID(build["generations"][key]) for key in CAPABILITIES):
                raise RuntimeError("unexpected active generation set in disposable copy")
            log.emit("provider", "verified previously activated disposable alias")
        active_alias = await store.resolve_active_multilingual_v2_alias_digest()
        if not active_alias:
            raise RuntimeError("disposable alias has no active digest")
    finally:
        await store.close()
    write_json(
        logs / "provider_activation.json",
        {
            **authorization,
            "alias_set_digest": active_alias,
            "generation_ids": [build["generations"][key] for key in CAPABILITIES],
            "vector_space": build["vector_space"],
            "model_revision": build["model_revision"],
            "authorization_digest": authorization_digest,
        },
    )


async def deactivate_unverified_alias(plan: dict[str, Any], runtime: Path, logs: Path) -> bool:
    """Undo only this run's first disposable V2 activation after a failed check."""
    from mnemo.storage.sqlite import SQLiteStore

    build = json.loads((logs / "provider_results.json").read_text(encoding="utf-8"))
    authorization = {
        "scope": "isolated-disposable-evaluation-only",
        "run_key": plan["run_key"],
        "actor_id": str(UUID(str(plan["disposable_actor_id"]))),
        "notebook_ids": build["notebook_ids"],
        "generations": build["generations"],
        "profile_fingerprint": build["profile_fingerprint"],
    }
    authorization_digest = hashlib.sha256(
        json.dumps(authorization, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    store = SQLiteStore(runtime / "mnemo.db")
    await store.open()
    try:
        active = await store.resolve_active_multilingual_v2_alias_digest()
        if active is None:
            return False
        await store.deactivate_first_multilingual_v2_alias_set(
            expected_active_alias_set_digest=active,
            authorization_id=uuid5(NAMESPACE_URL, authorization_digest),
            authorization_digest=authorization_digest,
        )
        if await store.resolve_active_multilingual_v2_alias_digest() is not None:
            raise RuntimeError("disposable alias remained active after recovery")
    finally:
        await store.close()
    receipt = logs / "provider_activation.json"
    if receipt.exists():
        recovered = (
            logs
            / f"provider_activation.recovered.{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.json"
        )
        os.replace(receipt, recovered)
    return True


async def execute() -> int:
    plan, records = preflight()
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("local CUDA BGE-M3 execution is unavailable; no run files were created")
    run_id, runtime, logs = run_paths(plan)
    verify_output_boundary(runtime, logs)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    with exclusive_run(logs / "run.lock"):
        return await _execute_locked(plan, records, run_id, runtime, logs)


async def _execute_locked(
    plan: dict[str, Any],
    records: dict[str, dict[str, Any]],
    run_id: str,
    runtime: Path,
    logs: Path,
) -> int:
    log = Log(logs / "events.jsonl", run_id)
    marker = runtime / "owner.json"
    identity = {
        "schema": "mnemo.phase86-disposable-run/1",
        "run_id": run_id,
        "plan_sha256": digest(PLAN),
        "snapshot_sha256": plan["existing_notebook"]["snapshot_sha256"],
    }
    if marker.exists():
        if json.loads(marker.read_text(encoding="utf-8")) != identity:
            raise RuntimeError("existing run directory belongs to another plan")
    elif any(runtime.iterdir()):
        raise RuntimeError("unowned existing run directory")
    else:
        write_json(marker, identity)
    previous_manifest = logs / "run_manifest.json"
    previous_audit_digest: str | None = None
    if previous_manifest.exists():
        previous = json.loads(previous_manifest.read_text(encoding="utf-8"))
        if any(previous.get(key) != value for key, value in identity.items()):
            raise RuntimeError("existing log directory belongs to another run")
        if previous.get("identity_qrel_blueprint_sha256") != digest(
            ROOT / "config/evaluation/phase86_dere3_identity_qrels.v1.json"
        ):
            raise RuntimeError("identity QREL blueprint changed during an existing run")
        previous_audit_digest = previous.get("pre_activation_audit_sha256")
        if previous_audit_digest is not None and (
            not (logs / "pre_activation_audit.json").is_file()
            or digest(logs / "pre_activation_audit.json") != previous_audit_digest
        ):
            raise RuntimeError("frozen audit receipt differs from the previous run manifest")
    elif any(path.name not in {"run.lock"} for path in logs.iterdir()):
        raise RuntimeError("unowned existing log directory")
    archive = archive_quarantined_attempt(logs)
    if archive is not None:
        log.emit("recovery", f"preserved previous quarantined receipts: {archive.name}")
    if "created_at" not in plan:
        created = logs / "run_manifest.json"
        if created.exists():
            plan["created_at"] = json.loads(created.read_text(encoding="utf-8"))["created_at"]
        else:
            plan["created_at"] = datetime.now(UTC).isoformat()
    write_json(
        logs / "run_manifest.json",
        {
            **identity,
            "created_at": plan["created_at"],
            "notebooks": {key: str(value) for key, value in notebook_ids(plan).items()},
            "existing_notebook": plan["existing_notebook"]["id"],
            "source_manifest": plan["source_manifest"],
            "source_manifest_sha256": plan["source_manifest_sha256"],
            "identity_qrel_blueprint_sha256": digest(
                ROOT / "config/evaluation/phase86_dere3_identity_qrels.v1.json"
            ),
            **(
                {"pre_activation_audit_sha256": previous_audit_digest}
                if previous_audit_digest is not None
                else {}
            ),
        },
    )
    promotion_attempted = False
    try:
        prepare_copy(plan, runtime, log)
        from mnemo_server.services.scope_authority import SQLiteNotebookScopeAuthority

        authority = SQLiteNotebookScopeAuthority(runtime / "acl.db")
        authority.initialize()
        await recover_before_notebook_resume(plan, records, runtime, logs, authority, log)
        await create_notebooks(plan, runtime / "mnemo.db", authority, log)
        await link_sources(plan, records, runtime, logs, log)
        build = await build_generations(plan, runtime, logs, log)
        with sqlite3.connect(runtime / "mnemo.db") as isolated_db:
            checkpoint = isolated_db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint is not None and checkpoint[0] != 0:
                raise RuntimeError("disposable database could not be checkpointed for audit")
        from scripts.audit_phase86_four_notebooks import audit

        with sqlite3.connect(
            f"file:{(runtime / 'mnemo.db').resolve().as_posix()}?mode=ro", uri=True
        ) as isolated:
            active = isolated.execute(
                "SELECT alias_set_digest FROM active_multilingual_v2_alias_set"
            ).fetchall()
        pre_audit = logs / "pre_activation_audit.json"
        if active:
            # A prior process may have died between promotion and verification.
            # Never infer a passing audit merely from an active SQLite alias.
            if not pre_audit.is_file() or previous_audit_digest is None:
                raise RuntimeError("active disposable alias has no prior passing audit receipt")
            audited_digest = digest(pre_audit)
        else:
            result = audit(plan, records, runtime, logs, require_active_alias=False)
            audited_digest = commit_pre_activation_audit(logs, result)
        manifest = json.loads((logs / "run_manifest.json").read_text(encoding="utf-8"))
        manifest["pre_activation_audit_sha256"] = audited_digest
        write_json(logs / "run_manifest.json", manifest)
        write_json(
            logs / "run_state.json",
            {"status": "PROMOTING", "pre_activation_audit_sha256": audited_digest},
        )
        promotion_attempted = True
        await promote_audited_alias(plan, runtime, logs, log, build, audited_digest)
        result = audit(plan, records, runtime, logs, require_active_alias=True)
        if result["status"] != "PASS":
            raise RuntimeError(f"post-promotion independent audit failed: {result['errors']}")
        from scripts.phase86_identity_qrels import bind_qrels

        qrels = bind_qrels(plan, records, runtime, logs, notebook_ids(plan))
        result["bound_qrels_sha256"] = digest(qrels)
        result["bound_qrels_path"] = str(qrels)
        result["pre_activation_audit_sha256"] = audited_digest
        result["status"] = "PASS"
        write_json(logs / "ingestion_summary.json", result)
        write_json(
            logs / "run_state.json",
            {
                "status": "SUCCEEDED",
                "pre_activation_audit_sha256": audited_digest,
                "bound_qrels_sha256": digest(qrels),
            },
        )
        log.emit("final", f"audit status {result['status']}")
        return 0
    except BaseException as error:
        rollback_error: str | None = None
        if promotion_attempted:
            try:
                if await deactivate_unverified_alias(plan, runtime, logs):
                    log.emit("provider", "unverified disposable alias deactivated")
            except Exception as recovery_error:
                rollback_error = f"{type(recovery_error).__name__}: {recovery_error}"
        write_json(
            logs / "run_state.json",
            {
                "status": "QUARANTINED",
                "error_type": type(error).__name__,
                "alias_recovery_error": rollback_error,
            },
        )
        write_json(
            logs / "ingestion_summary.json",
            {
                "status": "FAIL",
                "error_type": type(error).__name__,
                "message": str(error),
                "run_id": run_id,
                "alias_recovery_error": rollback_error,
            },
        )
        log.emit("final", f"FAIL: {type(error).__name__}: {error}")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("dry-run", "run"))
    args = parser.parse_args()
    plan, _records = preflight()
    run_id, runtime, logs = run_paths(plan)
    verify_output_boundary(runtime, logs)
    if args.mode == "dry-run":
        from scripts.phase86_identity_qrels import load_blueprint

        print(
            json.dumps(
                {
                    "status": "PREFLIGHT_PASS",
                    "run_id": run_id,
                    "existing_notebook": plan["existing_notebook"]["id"],
                    "new_notebooks": {key: str(value) for key, value in notebook_ids(plan).items()},
                    "source_count": sum(len(item["files"]) for item in plan["notebooks"].values()),
                    "identity_qrel_cases": len(load_blueprint(plan, _records)["cases"]),
                    "runtime": str(runtime),
                    "logs": str(logs),
                    "snapshot_copy_only": True,
                },
                indent=2,
            )
        )
        return 0
    return asyncio.run(execute())


if __name__ == "__main__":
    sys.exit(main())
