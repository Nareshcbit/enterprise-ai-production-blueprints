from plugins.classifier import (
    COMPLEX_TOKEN_THRESHOLD,
    Tier,
    classify,
    estimate_tokens,
    last_user_text,
)


def _messages(text: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": text}]


def test_estimate_tokens_counts_about_four_characters_per_token() -> None:
    assert estimate_tokens(_messages("a" * 400)) == 100


def test_estimate_tokens_sums_all_messages() -> None:
    messages = [
        {"role": "system", "content": "a" * 40},
        {"role": "user", "content": "b" * 40},
    ]
    assert estimate_tokens(messages) == 20


def test_estimate_tokens_reads_text_parts_of_multipart_content() -> None:
    messages = [{"role": "user", "content": [{"type": "text", "text": "a" * 80}]}]
    assert estimate_tokens(messages) == 20


def test_estimate_tokens_ignores_missing_content() -> None:
    assert estimate_tokens([{"role": "assistant", "content": None}]) == 0


def test_short_untagged_request_is_standard() -> None:
    assert classify(_messages("Extract the invoice number."), tags=[]) is Tier.STANDARD


def test_request_over_threshold_is_complex() -> None:
    long_text = "a" * (COMPLEX_TOKEN_THRESHOLD * 4 + 4)
    assert classify(_messages(long_text), tags=[]) is Tier.COMPLEX


def test_request_exactly_at_threshold_is_standard() -> None:
    at_threshold = "a" * (COMPLEX_TOKEN_THRESHOLD * 4)
    assert classify(_messages(at_threshold), tags=[]) is Tier.STANDARD


def test_short_request_tagged_reasoning_is_complex() -> None:
    assert (
        classify(_messages("Is this clause enforceable?"), tags=["reasoning"])
        is Tier.COMPLEX
    )


def test_last_user_text_returns_the_latest_user_message() -> None:
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "an answer"},
        {"role": "user", "content": [{"type": "text", "text": "second question"}]},
    ]
    assert last_user_text(messages) == "second question"


def test_last_user_text_is_empty_without_user_messages() -> None:
    assert last_user_text([{"role": "system", "content": "x"}]) == ""
