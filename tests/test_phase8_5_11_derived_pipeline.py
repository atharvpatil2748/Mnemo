"""Focused contracts for the evaluation-notebook derived pipeline."""

from scripts.phase8_5_11_derived_pipeline import (
    VISION_PROMPT_TEMPLATE_ID,
    VISION_RESPONSE_SCHEMA,
    VISION_SYSTEM_PROMPT,
    VISION_USER_PROMPT,
    vision_prompt_hash,
)


def test_vision_v2_contract_governs_low_information_images() -> None:
    assert VISION_PROMPT_TEMPLATE_ID == "mnemo-vision-safe/v2"
    assert "No discernible visual content." in VISION_SYSTEM_PROMPT
    assert "non-empty string" in VISION_USER_PROMPT
    properties = VISION_RESPONSE_SCHEMA["properties"]
    assert isinstance(properties, dict)
    assert properties["caption"] == {"type": "string", "minLength": 1}
    assert properties["observations"] == {
        "type": "array",
        "items": {"type": "string"},
        "maxItems": 6,
    }


def test_vision_v2_prompt_contract_has_stable_digest() -> None:
    first = vision_prompt_hash()
    second = vision_prompt_hash()

    assert first == second
    assert len(first) == 64
    int(first, 16)
