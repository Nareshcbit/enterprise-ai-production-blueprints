"""Circuit breaker for the vLLM tier: reads vLLM's waiting-queue depth.

An unknown or too-long queue counts as congested, so the router sends the
request to Bedrock instead of piling onto (or waiting on) a busy or dead vLLM.
"""

import logging
import re

import httpx

MAX_QUEUE_DEPTH = 5.0
METRICS_TIMEOUT_SECONDS = 0.5

_WAITING_GAUGE = re.compile(
    r"^vllm:num_requests_waiting(?:\{[^}]*\})?\s+([0-9.eE+-]+)\s*$", re.MULTILINE
)

logger = logging.getLogger(__name__)


def parse_queue_depth(metrics_text: str) -> float | None:
    """Total vllm:num_requests_waiting across all models, or None if absent."""
    values = [float(match) for match in _WAITING_GAUGE.findall(metrics_text)]
    return sum(values) if values else None


def is_congested(queue_depth: float | None) -> bool:
    """Unknown depth counts as congested, so a dead vLLM never receives traffic."""
    return queue_depth is None or queue_depth > MAX_QUEUE_DEPTH


async def fetch_queue_depth(
    client: httpx.AsyncClient, metrics_url: str
) -> float | None:
    try:
        response = await client.get(metrics_url, timeout=METRICS_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as error:
        logger.warning("vLLM metrics unavailable at %s: %s", metrics_url, error)
        return None
    return parse_queue_depth(response.text)
