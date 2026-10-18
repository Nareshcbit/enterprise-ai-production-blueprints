import httpx
import pytest

from plugins.circuit_breaker import fetch_queue_depth, is_congested, parse_queue_depth

METRICS_TEXT = """\
# HELP vllm:num_requests_waiting Number of requests waiting to be processed.
# TYPE vllm:num_requests_waiting gauge
vllm:num_requests_waiting{model_name="qwen2.5-7b-awq"} 3.0
vllm:num_requests_running{model_name="qwen2.5-7b-awq"} 8.0
"""


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_parse_queue_depth_reads_waiting_gauge() -> None:
    assert parse_queue_depth(METRICS_TEXT) == 3.0


def test_parse_queue_depth_sums_across_models() -> None:
    text = 'vllm:num_requests_waiting{model_name="a"} 2.0\nvllm:num_requests_waiting{model_name="b"} 4.0\n'
    assert parse_queue_depth(text) == 6.0


def test_parse_queue_depth_returns_none_when_metric_missing() -> None:
    assert parse_queue_depth("# nothing here\n") is None


@pytest.mark.parametrize(
    ("depth", "expected"),
    [(None, True), (0.0, False), (5.0, False), (5.1, True), (12.0, True)],
)
def test_is_congested(depth: float | None, expected: bool) -> None:
    assert is_congested(depth) is expected


async def test_fetch_queue_depth_returns_parsed_value() -> None:
    async with _client(
        lambda request: httpx.Response(200, text=METRICS_TEXT)
    ) as client:
        assert await fetch_queue_depth(client, "http://vllm/metrics") == 3.0


async def test_fetch_queue_depth_returns_none_on_http_error() -> None:
    async with _client(lambda request: httpx.Response(503)) as client:
        assert await fetch_queue_depth(client, "http://vllm/metrics") is None


async def test_fetch_queue_depth_returns_none_on_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    async with _client(handler) as client:
        assert await fetch_queue_depth(client, "http://vllm/metrics") is None


async def test_fetch_queue_depth_returns_none_when_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async with _client(handler) as client:
        assert await fetch_queue_depth(client, "http://vllm/metrics") is None
