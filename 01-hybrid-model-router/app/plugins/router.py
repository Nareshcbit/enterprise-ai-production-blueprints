"""LiteLLM pre-call hook: picks vLLM or Bedrock for each request.

Requests sent to the "auto" model are classified. Hard rules (reasoning tag,
long prompts) send a request straight to Bedrock. Otherwise the semantic cache
may override the rules with an LLM judge's earlier verdict for a similar prompt;
on a miss the judge runs in the background to fill the cache. Standard requests
go to vLLM unless the circuit breaker finds it congested or unreachable; then
they fail over to Bedrock.
"""

import asyncio
import hashlib
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from litellm.integrations.custom_logger import CustomLogger

from plugins.circuit_breaker import fetch_queue_depth, is_congested
from plugins.classifier import Tier, classify, last_user_text
from plugins.semantic_cache import CacheMode, SemanticCache, SemanticRouting

ROUTER_MODEL = "auto"
VLLM_MODEL = "vllm-local"
BEDROCK_MODEL = "bedrock-claude"

JUDGE_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "judge.md"
DEFAULT_SIMILARITY_THRESHOLD = (
    0.80  # bge-small: same-task pairs ~0.8-0.9, unrelated ~0.5
)
CACHE_MAX_ENTRIES = 50_000

logger = logging.getLogger(__name__)


class RouterHook(CustomLogger):
    def __init__(
        self,
        metrics_url: str,
        client: httpx.AsyncClient | None = None,
        semantic: SemanticRouting | None = None,
    ) -> None:
        super().__init__()
        self.metrics_url = metrics_url
        self.client = client or httpx.AsyncClient()
        self.semantic = semantic
        self._background_judges: set[asyncio.Task[None]] = set()

    async def _judge_and_store(
        self, semantic: SemanticRouting, key: str, text: str, vector: np.ndarray
    ) -> None:
        try:
            tier = await semantic.judge.judge(text)
            if tier is not None:
                semantic.cache.add(vector, tier)
                logger.info(
                    "route.judged tier=%s cached=%d",
                    tier.value,
                    len(semantic.cache),
                )
        finally:
            semantic.cache.release(key)

    def _judge_in_background(
        self, semantic: SemanticRouting, text: str, vector: np.ndarray
    ) -> None:
        key = hashlib.sha256(text.encode()).hexdigest()
        if not semantic.cache.claim(key):
            return
        task = asyncio.create_task(self._judge_and_store(semantic, key, text, vector))
        self._background_judges.add(task)
        task.add_done_callback(self._background_judges.discard)

    async def wait_for_background_judges(self) -> None:
        await asyncio.gather(*self._background_judges)

    async def _semantic_tier(
        self, semantic: SemanticRouting, messages: list[dict[str, Any]], rule_tier: Tier
    ) -> Tier:
        """The cached tier for a similar prompt in active mode; otherwise the rule tier."""
        text = last_user_text(messages)
        if not text:
            return rule_tier
        try:
            vector = await semantic.embedder.embed(text)
        except Exception:  # embedding failure must not break routing
            logger.exception("Embedding failed; routing by rules")
            return rule_tier
        hit = semantic.cache.lookup(vector)
        if hit is None:
            self._judge_in_background(semantic, text, vector)
            logger.info(
                "route.decision source=rule mode=%s cache=miss",
                semantic.mode.value,
            )
            return rule_tier
        use_cache = semantic.mode is CacheMode.ACTIVE
        logger.info(
            "route.decision source=%s mode=%s cache=hit cached_tier=%s rule_tier=%s similarity=%.3f",
            "cache" if use_cache else "rule",
            semantic.mode.value,
            hit.tier.value,
            rule_tier.value,
            hit.similarity,
        )
        return hit.tier if use_cache else rule_tier

    async def _choose_model(self, data: dict[str, Any]) -> str:
        messages = data.get("messages") or []
        tags = (data.get("metadata") or {}).get("tags") or []
        tier = classify(messages, tags)
        if tier is Tier.STANDARD and self.semantic is not None:
            tier = await self._semantic_tier(self.semantic, messages, rule_tier=tier)
        if tier is Tier.COMPLEX:
            return BEDROCK_MODEL
        queue_depth = await fetch_queue_depth(self.client, self.metrics_url)
        return BEDROCK_MODEL if is_congested(queue_depth) else VLLM_MODEL

    async def async_pre_call_hook(
        self, user_api_key_dict: Any, cache: Any, data: dict[str, Any], call_type: Any
    ) -> dict[str, Any]:
        if data.get("model") != ROUTER_MODEL:
            return data
        data["model"] = await self._choose_model(data)
        logger.info("route.chosen model=%s", data["model"])
        return data


def _configure_plugin_logging() -> None:
    """LiteLLM only surfaces warnings from other loggers; show plugin INFO lines."""
    plugins_logger = logging.getLogger("plugins")
    if plugins_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    plugins_logger.addHandler(handler)
    plugins_logger.setLevel(logging.INFO)
    plugins_logger.propagate = False


def build_semantic_routing_from_env() -> SemanticRouting | None:
    mode = CacheMode(os.environ.get("ROUTER_CACHE_MODE", CacheMode.OFF.value))
    if mode is CacheMode.OFF:
        return None
    # Imported here so the default (off) path never loads ONNX Runtime.
    from plugins.embedder import DIMENSIONS, FastEmbedEmbedder
    from plugins.judge import LLMJudge

    threshold = float(
        os.environ.get("CACHE_SIMILARITY_THRESHOLD", DEFAULT_SIMILARITY_THRESHOLD)
    )
    return SemanticRouting(
        embedder=FastEmbedEmbedder(),
        cache=SemanticCache(DIMENSIONS, threshold, CACHE_MAX_ENTRIES),
        judge=LLMJudge(
            model=os.environ["JUDGE_MODEL"],
            prompt=JUDGE_PROMPT_PATH.read_text(),
            aws_region_name=os.environ["AWS_REGION"],
        ),
        mode=mode,
    )


_configure_plugin_logging()
router_hook = RouterHook(
    metrics_url=os.environ.get("VLLM_METRICS_URL", "http://localhost:8000/metrics"),
    semantic=build_semantic_routing_from_env(),
)
