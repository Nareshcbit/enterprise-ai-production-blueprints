import httpx
import numpy as np

from plugins.classifier import Tier
from plugins.router import (
    BEDROCK_MODEL,
    ROUTER_MODEL,
    VLLM_MODEL,
    RouterHook,
)
from plugins.semantic_cache import CacheMode, SemanticCache, SemanticRouting

METRICS_TEXT = 'vllm:num_requests_waiting{model_name="qwen2.5-7b-awq"} 3.0\n'


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _request(
    text: str, tags: list[str] | None = None, model: str = ROUTER_MODEL
) -> dict:
    data: dict = {"model": model, "messages": [{"role": "user", "content": text}]}
    if tags is not None:
        data["metadata"] = {"tags": tags}
    return data


async def _route(data: dict, metrics_handler) -> dict:
    async with _client(metrics_handler) as client:
        hook = RouterHook(metrics_url="http://vllm/metrics", client=client)
        return await hook.async_pre_call_hook(None, None, data, "completion")


async def test_standard_request_goes_to_vllm_when_queue_is_short() -> None:
    result = await _route(
        _request("Extract the date."), lambda r: httpx.Response(200, text=METRICS_TEXT)
    )
    assert result["model"] == VLLM_MODEL


async def test_standard_request_fails_over_to_bedrock_when_queue_is_long() -> None:
    busy = 'vllm:num_requests_waiting{model_name="m"} 9.0\n'
    result = await _route(
        _request("Extract the date."), lambda r: httpx.Response(200, text=busy)
    )
    assert result["model"] == BEDROCK_MODEL


async def test_standard_request_fails_over_to_bedrock_when_vllm_is_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = await _route(_request("Extract the date."), handler)
    assert result["model"] == BEDROCK_MODEL


async def test_reasoning_request_goes_to_bedrock_without_checking_vllm() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("metrics should not be fetched for complex requests")

    result = await _route(
        _request("Is this clause enforceable?", tags=["reasoning"]), handler
    )
    assert result["model"] == BEDROCK_MODEL


async def test_request_naming_a_specific_model_is_left_alone() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("metrics should not be fetched for explicit models")

    result = await _route(_request("hi", model=VLLM_MODEL), handler)
    assert result["model"] == VLLM_MODEL


# --- Semantic cache step -----------------------------------------------------


def QUIET_VLLM(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text=METRICS_TEXT)


VECTORS = {
    "Extract the invoice number from INV-1.": np.array([1, 0, 0], dtype=np.float32),
    "Extract the invoice number from INV-2.": np.array(
        [0.99, 0.1, 0], dtype=np.float32
    ),
    "Compare liability in contracts A and B.": np.array([0, 1, 0], dtype=np.float32),
    "Compare indemnity in contracts C and D.": np.array(
        [0.1, 0.99, 0], dtype=np.float32
    ),
}


class FakeEmbedder:
    async def embed(self, text: str) -> np.ndarray:
        return VECTORS[text]


class FakeJudge:
    def __init__(self, verdicts: dict[str, Tier | None]) -> None:
        self.verdicts = verdicts
        self.calls: list[str] = []

    async def judge(self, text: str) -> Tier | None:
        self.calls.append(text)
        return self.verdicts.get(text)


def _semantic(mode: CacheMode, judge: FakeJudge) -> SemanticRouting:
    cache = SemanticCache(dimensions=3, threshold=0.9, max_entries=100)
    return SemanticRouting(embedder=FakeEmbedder(), cache=cache, judge=judge, mode=mode)


async def _route_all(texts: list[str], semantic: SemanticRouting) -> list[str]:
    """Route each request in turn, letting background judges finish in between."""
    models = []
    async with _client(QUIET_VLLM) as client:
        hook = RouterHook(
            metrics_url="http://vllm/metrics", client=client, semantic=semantic
        )
        for text in texts:
            result = await hook.async_pre_call_hook(
                None, None, _request(text), "completion"
            )
            models.append(result["model"])
            await hook.wait_for_background_judges()
    return models


async def test_cache_miss_routes_by_rules_and_judges_in_background() -> None:
    judge = FakeJudge({"Compare liability in contracts A and B.": Tier.COMPLEX})
    semantic = _semantic(CacheMode.ACTIVE, judge)
    models = await _route_all(["Compare liability in contracts A and B."], semantic)
    assert models == [VLLM_MODEL]
    assert judge.calls == ["Compare liability in contracts A and B."]
    assert len(semantic.cache) == 1


async def test_active_mode_cache_hit_overrides_rules() -> None:
    judge = FakeJudge({"Compare liability in contracts A and B.": Tier.COMPLEX})
    models = await _route_all(
        [
            "Compare liability in contracts A and B.",
            "Compare indemnity in contracts C and D.",
        ],
        _semantic(CacheMode.ACTIVE, judge),
    )
    assert models == [VLLM_MODEL, BEDROCK_MODEL]
    assert judge.calls == ["Compare liability in contracts A and B."]


async def test_active_mode_cache_hit_can_confirm_standard() -> None:
    judge = FakeJudge({"Extract the invoice number from INV-1.": Tier.STANDARD})
    models = await _route_all(
        [
            "Extract the invoice number from INV-1.",
            "Extract the invoice number from INV-2.",
        ],
        _semantic(CacheMode.ACTIVE, judge),
    )
    assert models == [VLLM_MODEL, VLLM_MODEL]
    assert len(judge.calls) == 1


async def test_shadow_mode_cache_hit_does_not_change_routing() -> None:
    judge = FakeJudge({"Compare liability in contracts A and B.": Tier.COMPLEX})
    models = await _route_all(
        [
            "Compare liability in contracts A and B.",
            "Compare indemnity in contracts C and D.",
        ],
        _semantic(CacheMode.SHADOW, judge),
    )
    assert models == [VLLM_MODEL, VLLM_MODEL]


async def test_failed_judge_leaves_cache_empty() -> None:
    judge = FakeJudge({})
    semantic = _semantic(CacheMode.ACTIVE, judge)
    await _route_all(["Compare liability in contracts A and B."], semantic)
    assert len(semantic.cache) == 0


async def test_hard_rules_skip_the_cache_and_judge() -> None:
    judge = FakeJudge({})
    data = _request("Compare liability in contracts A and B.", tags=["reasoning"])
    async with _client(QUIET_VLLM) as client:
        hook = RouterHook(
            metrics_url="http://vllm/metrics",
            client=client,
            semantic=_semantic(CacheMode.ACTIVE, judge),
        )
        result = await hook.async_pre_call_hook(None, None, data, "completion")
        await hook.wait_for_background_judges()
    assert result["model"] == BEDROCK_MODEL
    assert judge.calls == []


async def test_concurrent_misses_judge_a_prompt_only_once() -> None:
    judge = FakeJudge({"Compare liability in contracts A and B.": Tier.COMPLEX})
    async with _client(QUIET_VLLM) as client:
        hook = RouterHook(
            metrics_url="http://vllm/metrics",
            client=client,
            semantic=_semantic(CacheMode.ACTIVE, judge),
        )
        for _ in range(3):
            data = _request("Compare liability in contracts A and B.")
            await hook.async_pre_call_hook(None, None, data, "completion")
        await hook.wait_for_background_judges()
    assert len(judge.calls) == 1
