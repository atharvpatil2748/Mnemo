"""Run the reproducible local Phase 8.5.11 model-candidate benchmarks."""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import sqlite3
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from sentence_transformers import CrossEncoder, SentenceTransformer
from transformers import CLIPModel, CLIPProcessor

EMBEDDING_MODELS = {
    "multilingual-e5-small": "models--intfloat--multilingual-e5-small",
    "paraphrase-multilingual-MiniLM-L12-v2": (
        "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"
    ),
    "bge-m3": "models--BAAI--bge-m3",
}
RERANKER_MODELS = {
    "bge-reranker-v2-m3": "models--BAAI--bge-reranker-v2-m3",
    "bert-base-multilingual-cased-reranker": (
        "models--PMJAi--bert-base-multilingual-cased-reranker"
    ),
    "distilbert-base-multilingual-cased-reranker": (
        "models--PMJAi--distilbert-base-multilingual-cased-sl_200-reranker"
    ),
}
VISUAL_MODELS = {
    "clip-vit-base-patch32": "models--openai--clip-vit-base-patch32",
    "clip-vit-base-patch16": "models--openai--clip-vit-base-patch16",
    "clip-vit-large-patch14": "models--openai--clip-vit-large-patch14",
}

# One stable relevance label per real query. Hindi-source retrieval cannot be
# measured because the evaluation corpus contains no canonical Hindi document.
QUERIES = (
    ("What technical skills are listed in Atharv's resume?", "en", "Atharv_Patil_RESUME_SDE.pdf"),
    ("अथर्व के रिज्यूमे में कौन से तकनीकी कौशल हैं?", "hi", "Atharv_Patil_RESUME_SDE.pdf"),
    ("अथर्वच्या रिझ्युमेमध्ये कोणती तांत्रिक कौशल्ये आहेत?", "mr", "Atharv_Patil_RESUME_SDE.pdf"),
    ("When did the Marathi book begin?", "en", "manuscript.pdf"),
    ("मराठी पुस्तक की शुरुआत किस तारीख को हुई?", "hi", "manuscript.pdf"),
    ("माझ्या पुस्तकाची सुरुवात कोणत्या तारखेला झाली?", "mr", "manuscript.pdf"),
    ("Who is ranked first in the Y24 CPI list?", "en", "Y24_CPI.csv"),
    ("Y24 CPI सूची में पहला स्थान किसका है?", "hi", "Y24_CPI.csv"),
    ("Y24 CPI यादीत प्रथम क्रमांक कोणाचा आहे?", "mr", "Y24_CPI.csv"),
    (
        "What machining processes are included in the ME361 syllabus?",
        "en",
        "ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1)",
    ),
    (
        "ME361 पाठ्यक्रम में कौन सी मशीनिंग प्रक्रियाएँ हैं?",
        "hi",
        "ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1)",
    ),
    (
        "ME361 अभ्यासक्रमात कोणत्या मशीनिंग प्रक्रिया आहेत?",
        "mr",
        "ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1)",
    ),
    (
        "Why did the old aunt call a village panchayat?",
        "en",
        "Act 2. panch-parmeshwar-by-munshi-premchand.pdf",
    ),
    ("बूढ़ी खाला ने पंचायत क्यों बुलाई?", "hi", "Act 2. panch-parmeshwar-by-munshi-premchand.pdf"),
    ("वृद्ध खालाने पंचायत का बोलावली?", "mr", "Act 2. panch-parmeshwar-by-munshi-premchand.pdf"),
    ("Which endpoint in server.js reports health?", "en", "server.js"),
    ("server.js में स्वास्थ्य स्थिति कौन सा endpoint देता है?", "hi", "server.js"),
    ("server.js मध्ये आरोग्य स्थिती कोणता endpoint देतो?", "mr", "server.js"),
)

# The current pack has canonical English documents plus one Marathi manuscript;
# it intentionally has no canonical Hindi source document. Query language and
# source language are kept separate so unsupported directions are not implied.
SOURCE_LANGUAGES = {
    "manuscript.pdf": "mr",
}


def _snapshot(hub: Path, repository: str) -> Path:
    snapshots = sorted((hub / repository / "snapshots").iterdir())
    if not snapshots:
        raise RuntimeError(f"no downloaded snapshot for {repository}")
    return snapshots[-1]


def _documents(database: Path) -> tuple[list[str], list[str]]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT json_extract(v.metadata, '$.title') AS title, "
            "group_concat(c.text, char(10)) AS content "
            "FROM document_versions v LEFT JOIN chunks c ON c.version_id=v.version_id "
            "GROUP BY v.version_id ORDER BY title"
        ).fetchall()
        titles = [str(row["title"]) for row in rows]
        texts = [f"title: {row['title']}\n{str(row['content'] or '')[:2500]}" for row in rows]
        return titles, texts
    finally:
        connection.close()


def _metrics(rankings: list[list[int]], expected: list[int]) -> dict[str, float]:
    reciprocal: list[float] = []
    ndcg: list[float] = []
    recalls = {1: 0, 5: 0, 10: 0}
    for order, target in zip(rankings, expected, strict=True):
        rank = order.index(target) + 1
        reciprocal.append(1.0 / rank)
        ndcg.append(1.0 / math.log2(rank + 1))
        for limit in recalls:
            recalls[limit] += int(rank <= limit)
    total = len(expected)
    return {
        "recall_at_1": recalls[1] / total,
        "recall_at_5": recalls[5] / total,
        "recall_at_10": recalls[10] / total,
        "mrr": statistics.fmean(reciprocal),
        "ndcg": statistics.fmean(ndcg),
    }


def _direction_metrics(
    rankings: list[list[int]], expected: list[int]
) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, tuple[list[list[int]], list[int]]] = {}
    for ranking, target, (_, query_language, title) in zip(
        rankings, expected, QUERIES, strict=True
    ):
        source_language = SOURCE_LANGUAGES.get(title, "en")
        key = f"{query_language}->{source_language}"
        group_rankings, group_expected = grouped.setdefault(key, ([], []))
        group_rankings.append(ranking)
        group_expected.append(target)
    return {
        key: {"samples": len(group_expected), **_metrics(group_rankings, group_expected)}
        for key, (group_rankings, group_expected) in sorted(grouped.items())
    }


def _latency(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "average_ms": round(statistics.fmean(values), 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)], 3),
    }


def _disk_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _benchmark_embeddings(hub: Path, titles: list[str], texts: list[str]) -> list[dict[str, Any]]:
    expected = [titles.index(title) for _, _, title in QUERIES]
    results: list[dict[str, Any]] = []
    for name, repository in EMBEDDING_MODELS.items():
        path = _snapshot(hub, repository)
        started = time.perf_counter()
        model = SentenceTransformer(str(path), device="cpu", trust_remote_code=True)
        document_vectors = model.encode(
            texts, batch_size=4, normalize_embeddings=True, convert_to_numpy=True
        )
        latencies: list[float] = []
        rankings: list[list[int]] = []
        for query, _, _ in QUERIES:
            tick = time.perf_counter()
            query_text = f"query: {query}" if name == "multilingual-e5-small" else query
            vector = model.encode([query_text], normalize_embeddings=True, convert_to_numpy=True)[0]
            latencies.append((time.perf_counter() - tick) * 1000)
            rankings.append(np.argsort(-(document_vectors @ vector)).tolist())
        results.append(
            {
                "model": name,
                "revision": path.name,
                "dimensions": int(document_vectors.shape[1]),
                "metrics": _metrics(rankings, expected),
                "direction_metrics": _direction_metrics(rankings, expected),
                "latency": _latency(latencies),
                "load_and_corpus_seconds": round(time.perf_counter() - started, 3),
                "disk_bytes": _disk_bytes(path),
                "failures": 0,
            }
        )
        del model, document_vectors
        gc.collect()
    return results


def _benchmark_rerankers(hub: Path, titles: list[str], texts: list[str]) -> list[dict[str, Any]]:
    target_titles = list(dict.fromkeys(title for _, _, title in QUERIES))
    distractors = [title for title in titles if title not in target_titles][:6]
    candidate_titles = target_titles + distractors
    candidate_indexes = [titles.index(title) for title in candidate_titles]
    expected = [candidate_titles.index(title) for _, _, title in QUERIES]
    candidates = [texts[index][:1200] for index in candidate_indexes]
    results: list[dict[str, Any]] = []
    for name, repository in RERANKER_MODELS.items():
        path = _snapshot(hub, repository)
        started = time.perf_counter()
        model = CrossEncoder(str(path), device="cpu", max_length=256, trust_remote_code=True)
        rankings: list[list[int]] = []
        latencies: list[float] = []
        for query, _, _ in QUERIES:
            tick = time.perf_counter()
            scores = np.asarray(
                model.predict([(query, candidate) for candidate in candidates], batch_size=12)
            ).reshape(-1)
            latencies.append((time.perf_counter() - tick) * 1000)
            rankings.append(np.argsort(-scores).tolist())
        results.append(
            {
                "model": name,
                "revision": path.name,
                "candidate_set": candidate_titles,
                "metrics": _metrics(rankings, expected),
                "direction_metrics": _direction_metrics(rankings, expected),
                "latency": _latency(latencies),
                "total_seconds": round(time.perf_counter() - started, 3),
                "disk_bytes": _disk_bytes(path),
                "failures": 0,
            }
        )
        del model
        gc.collect()
    return results


def _visual_inputs(
    corpus: Path, database: Path, derived_evidence: Path | None
) -> tuple[list[Path], list[str]]:
    paths = sorted(corpus.glob("*.jp*g"))
    labels = [
        "an airline boarding pass",
        "a person or outdoor scene",
        "a person or indoor scene",
        "a document or screen photograph",
        "a document or screen photograph",
        "a person or indoor scene",
        "a person or indoor scene",
        "a document or screen photograph",
    ]
    if len(paths) != len(labels):
        raise RuntimeError("visual benchmark expects the eight discovered JPEG fixtures")
    if derived_evidence is not None:
        evidence = json.loads(derived_evidence.read_text(encoding="utf-8"))
        embedded_labels = {
            "Atharv_Patil_240740.pdf": "handwritten mathematics with rotation matrices",
            "Bhagavad-gita As It Is with pics!": "Hindu devotional illustration with Krishna",
            "ME361_L1_fbd03201-7db3-4553-a6e5-06f24817f9ea (1)": "small magenta slide icon",
            "Coordinator Application 2026\u201327": "black t-shirt with green wolves and moon",
            "PHYSICS_JEE_ADVANCED.pdf": "handwritten mechanics notes about friction",
            "ME333 - Exp2-LabReport_To_Submit.docx": "frequency versus amplitude line chart",
        }
        blob_root = database.parent / "files"
        for item in evidence["selected_assets"]:
            if item["container_kind"] == "standalone":
                continue
            content_hash = item["content_hash"]
            blobs = sorted((blob_root / content_hash[:2] / content_hash[2:]).glob("raw.*"))
            if len(blobs) != 1:
                raise RuntimeError(f"expected one blob for visual asset {content_hash}")
            paths.append(blobs[0])
            labels.append(embedded_labels[item["title"]])
    return paths, labels


def _benchmark_visual(
    hub: Path, corpus: Path, database: Path, derived_evidence: Path | None
) -> list[dict[str, Any]]:
    paths, labels = _visual_inputs(corpus, database, derived_evidence)
    images = [Image.open(path).convert("RGB") for path in paths]
    expected = list(range(len(paths)))
    results: list[dict[str, Any]] = []
    for name, repository in VISUAL_MODELS.items():
        path = _snapshot(hub, repository)
        started = time.perf_counter()
        processor = CLIPProcessor.from_pretrained(path, local_files_only=True)
        model = CLIPModel.from_pretrained(path, local_files_only=True)
        tick = time.perf_counter()
        inputs = processor(text=labels, images=images, return_tensors="pt", padding=True)
        with torch.no_grad():
            output = model(**inputs)
        image_vectors = output.image_embeds / output.image_embeds.norm(dim=1, keepdim=True)
        text_vectors = output.text_embeds / output.text_embeds.norm(dim=1, keepdim=True)
        elapsed = (time.perf_counter() - tick) * 1000
        rankings = torch.argsort(text_vectors @ image_vectors.T, descending=True).tolist()
        image_to_text_rankings = torch.argsort(
            image_vectors @ text_vectors.T, descending=True
        ).tolist()
        image_to_image_rankings = torch.argsort(
            image_vectors @ image_vectors.T, descending=True
        ).tolist()
        results.append(
            {
                "model": name,
                "revision": path.name,
                "dimensions": int(image_vectors.shape[1]),
                "text_to_image": _metrics(rankings, expected),
                "image_to_text": _metrics(image_to_text_rankings, expected),
                "image_to_image_identity": _metrics(image_to_image_rankings, expected),
                "batch_latency_ms": round(elapsed, 3),
                "per_image_ms": round(elapsed / len(images), 3),
                "total_seconds": round(time.perf_counter() - started, 3),
                "disk_bytes": _disk_bytes(path),
                "failures": 0,
            }
        )
        del model, processor, inputs, output, image_vectors, text_vectors
        gc.collect()
    for image in images:
        image.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--hub", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--derived-evidence", type=Path)
    parser.add_argument("--visual-only", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    database = args.database.resolve(strict=True)
    if args.visual_only:
        result = json.loads(args.output.read_text(encoding="utf-8"))
        result["visual_embeddings"] = _benchmark_visual(
            args.hub, args.corpus, database, args.derived_evidence
        )
        result["visual_fixture_count"] = 14
        result["visual_fixture_scope"] = "8 standalone + 6 embedded PDF/PPTX/DOCX"
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result["visual_embeddings"], ensure_ascii=False, indent=2))
        return
    titles, texts = _documents(database)
    result = {
        "profile": "phase8.5.11/local-cpu/v1",
        "documents": len(titles),
        "queries": [
            {"query": query, "language": language, "expected_document": title}
            for query, language, title in QUERIES
        ],
        "limitations": {
            "canonical_hindi_source": "not represented in evaluation corpus",
            "hardware": "CPU-only torch runtime",
        },
        "multilingual_embeddings": _benchmark_embeddings(args.hub, titles, texts),
        "multilingual_rerankers": _benchmark_rerankers(args.hub, titles, texts),
        "visual_embeddings": _benchmark_visual(
            args.hub, args.corpus, database, args.derived_evidence
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
