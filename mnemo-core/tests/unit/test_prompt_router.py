"""Unit tests for conservative query-intent prompt router."""

from __future__ import annotations

from mnemo.retrieval.answer import (
    CODE_TABLE_EXTRACTION_SYSTEM_PROMPT,
    CROSS_DOCUMENT_SYNTHESIS_SYSTEM_PROMPT,
    GROUNDED_ANSWER_SYSTEM_PROMPT,
    STRUCTURED_EXTRACTION_SYSTEM_PROMPT,
    classify_prompt_template,
)


def test_semantic_question_routes_to_s1_default():
    """General conceptual and semantic queries must route to S1 default."""
    assert (
        classify_prompt_template("What technical skills and background does Atharv have?")
        == GROUNDED_ANSWER_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template("What does the Bhagavad Gita teach about karma yoga and duty?")
        == GROUNDED_ANSWER_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template("Explain the main vision behind the Fine Arts Club application.")
        == GROUNDED_ANSWER_SYSTEM_PROMPT
    )


def test_exact_verse_and_numbers_route_to_s2():
    """Explicit exact verse and numerical tolerance questions route to S2."""
    assert (
        classify_prompt_template("Tell me Bhagavad Gita 2.47.")
        == STRUCTURED_EXTRACTION_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template("What is the exact verse text of Bhagavad Gita 18.66?")
        == STRUCTURED_EXTRACTION_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template("What are the exact CNC milling tolerances specified in ME361?")
        == STRUCTURED_EXTRACTION_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template("What is the exact estimated original mass calculated in ME333?")
        == STRUCTURED_EXTRACTION_SYSTEM_PROMPT
    )


def test_code_and_tabular_queries_route_to_s3():
    """Explicit code functions, endpoints, and CSV tabular lookups route to S3."""
    assert (
        classify_prompt_template("What HTTP endpoints and routes are defined in server.js?")
        == CODE_TABLE_EXTRACTION_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template("What does the function validateWhisperOutput do in server.js?")
        == CODE_TABLE_EXTRACTION_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template(
            "What is the CPI and rank of roll number 240740 in the Y24 CPI dataset?"
        )
        == CODE_TABLE_EXTRACTION_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template("Which student has rank 1 in the Y24 CPI csv table?")
        == CODE_TABLE_EXTRACTION_SYSTEM_PROMPT
    )


def test_cross_document_queries_route_to_s4():
    """Multi-document comparison and synthesis queries route to S4."""
    assert (
        classify_prompt_template(
            "Compare Atharv's CPI in his resume with the Y24 CPI dataset entry."
        )
        == CROSS_DOCUMENT_SYNTHESIS_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template(
            "How do the projects in Atharv's resume connect with the server.js codebase?"
        )
        == CROSS_DOCUMENT_SYNTHESIS_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template(
            "Compare the resume leadership positions with the Coordinator Application."
        )
        == CROSS_DOCUMENT_SYNTHESIS_SYSTEM_PROMPT
    )


def test_semantic_queries_with_numbers_remain_s1():
    """Semantic queries mentioning numbers without requesting exact extraction remain S1."""
    assert (
        classify_prompt_template("Why did Arjuna hesitate in Chapter 1 and Chapter 2?")
        == GROUNDED_ANSWER_SYSTEM_PROMPT
    )
    assert (
        classify_prompt_template(
            "Discuss the 4 main observations about resonance in the vibration lab."
        )
        == GROUNDED_ANSWER_SYSTEM_PROMPT
    )


def test_ambiguous_or_uncertain_queries_fallback_to_s1():
    """Uncertain or ambiguous queries must safely fall back to S1."""
    assert (
        classify_prompt_template("Tell me about the experiment.") == GROUNDED_ANSWER_SYSTEM_PROMPT
    )
    assert classify_prompt_template("What are the key details?") == GROUNDED_ANSWER_SYSTEM_PROMPT
