import asyncio
from types import SimpleNamespace
from typing import Any

from plugins.classifier import Tier
from plugins.judge import LLMJudge


def _response(content: str) -> SimpleNamespace:
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _judge_returning(
    content: str, calls: list[dict[str, Any]] | None = None
) -> LLMJudge:
    async def complete(**kwargs: Any) -> SimpleNamespace:
        if calls is not None:
            calls.append(kwargs)
        return _response(content)

    return LLMJudge(model="judge-model", prompt="Classify.", complete=complete)


async def test_simple_verdict_maps_to_standard_tier() -> None:
    judge = _judge_returning('{"tier": "simple", "reason": "extraction"}')
    assert await judge.judge("Extract the date.") is Tier.STANDARD


async def test_complex_verdict_maps_to_complex_tier() -> None:
    judge = _judge_returning('{"tier": "complex", "reason": "legal analysis"}')
    assert await judge.judge("Compare these clauses.") is Tier.COMPLEX


async def test_verdict_wrapped_in_code_fence_is_accepted() -> None:
    judge = _judge_returning('```json\n{"tier": "complex", "reason": "x"}\n```')
    assert await judge.judge("Compare these clauses.") is Tier.COMPLEX


async def test_malformed_json_returns_none() -> None:
    assert await _judge_returning("probably complex").judge("hi") is None


async def test_unknown_tier_returns_none() -> None:
    judge = _judge_returning('{"tier": "medium", "reason": "x"}')
    assert await judge.judge("hi") is None


async def test_backend_error_returns_none() -> None:
    async def complete(**kwargs: Any) -> SimpleNamespace:
        raise RuntimeError("Bedrock throttled")

    judge = LLMJudge(model="judge-model", prompt="Classify.", complete=complete)
    assert await judge.judge("hi") is None


async def test_slow_backend_times_out_and_returns_none() -> None:
    async def complete(**kwargs: Any) -> SimpleNamespace:
        await asyncio.sleep(1)
        return _response('{"tier": "simple", "reason": "x"}')

    judge = LLMJudge(
        model="judge-model", prompt="Classify.", complete=complete, timeout_seconds=0.01
    )
    assert await judge.judge("hi") is None


async def test_judge_sends_prompt_as_system_and_text_as_user() -> None:
    calls: list[dict[str, Any]] = []
    await _judge_returning('{"tier": "simple", "reason": "x"}', calls).judge(
        "Extract the date."
    )
    assert calls[0]["model"] == "judge-model"
    assert calls[0]["messages"] == [
        {"role": "system", "content": "Classify."},
        {"role": "user", "content": "Extract the date."},
    ]
