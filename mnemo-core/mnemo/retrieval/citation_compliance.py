"""ADR-0052/0054 strict final-publication citation validation."""

from __future__ import annotations

import re

from mnemo.interfaces import IntegrityError
from mnemo.models.answer import GroundedAnswerResult, GroundedAnswerStatus

CITATION_COMPLIANCE_CORRECTION = (
    "CITATION_COMPLIANCE_CORRECTION\n"
    "Generate a replacement answer only. Reuse the QUESTION and CONTEXT already supplied. "
    "Do not discuss, quote, or preserve the prior answer. Every evidence-backed claim must "
    "use only exact ASCII citations in the form [source:N], where N is an available Source "
    "number. Include at least one such citation. Do not use case variants, malformed markers, "
    "unavailable source numbers, or a references section."
)

_CANONICAL = re.compile(r"\[source:([1-9][0-9]*)\]", flags=re.ASCII)
_SOURCE_SHAPED = re.compile(r"\[source:", flags=re.ASCII | re.IGNORECASE)


def validate_final_publication(answer_result: GroundedAnswerResult) -> None:
    """Require canonical, selected-context markers without changing provider text."""
    if answer_result.status is GroundedAnswerStatus.NO_CONTEXT:
        return
    answer = answer_result.answer
    if answer is None:  # pragma: no cover - model invariant
        raise IntegrityError("citation_compliance: generated answer is unavailable")
    sources = {item.source_number for item in answer_result.context_result.items}
    found: list[int] = []
    position = 0
    while True:
        shaped = _SOURCE_SHAPED.search(answer, position)
        if shaped is None:
            break
        canonical = _CANONICAL.match(answer, shaped.start())
        if canonical is None:
            raise IntegrityError("citation_compliance: answer contains noncanonical source marker")
        number = int(canonical.group(1))
        if number not in sources:
            raise IntegrityError("citation_compliance: answer cites unavailable source number")
        found.append(number)
        position = canonical.end()
    if not found:
        raise IntegrityError("citation_compliance: generated final answer requires a source marker")
