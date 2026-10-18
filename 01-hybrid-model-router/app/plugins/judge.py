"""LLM judge: asks a model whether a prompt needs the strong tier."""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import litellm
from pydantic import BaseModel, ValidationError

from plugins.classifier import Tier

logger = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
_TIERS = {"simple": Tier.STANDARD, "complex": Tier.COMPLEX}


class Verdict(BaseModel):
    tier: Literal["simple", "complex"]
    reason: str


def parse_verdict(content: str) -> Verdict | None:
    try:
        return Verdict.model_validate(json.loads(_CODE_FENCE.sub("", content.strip())))
    except (json.JSONDecodeError, ValidationError) as error:
        logger.warning("Judge returned an unusable verdict: %s", error)
        return None


class LLMJudge:
    def __init__(
        self,
        model: str,
        prompt: str,
        complete: Callable[..., Awaitable[Any]] = litellm.acompletion,
        timeout_seconds: float = 5.0,
        **completion_kwargs: Any,
    ) -> None:
        self.model = model
        self.prompt = prompt
        self.complete = complete
        self.timeout_seconds = timeout_seconds
        self.completion_kwargs = completion_kwargs

    async def _ask(self, text: str) -> str:
        response = await self.complete(
            model=self.model,
            messages=[
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": text},
            ],
            max_tokens=100,
            temperature=0,
            **self.completion_kwargs,
        )
        return response.choices[0].message.content or ""

    async def judge(self, text: str) -> Tier | None:
        """The judge's tier for this prompt, or None if it couldn't decide."""
        try:
            content = await asyncio.wait_for(self._ask(text), self.timeout_seconds)
        except TimeoutError:
            logger.warning("Judge timed out after %.1fs", self.timeout_seconds)
            return None
        except Exception:  # any backend failure must not break routing
            logger.exception("Judge call failed")
            return None
        verdict = parse_verdict(content)
        return _TIERS[verdict.tier] if verdict else None
