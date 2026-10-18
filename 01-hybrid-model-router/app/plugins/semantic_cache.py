"""In-process cache of routing decisions, looked up by meaning.

Each entry is a prompt embedding and the tier an LLM judge chose for it. A new
prompt reuses the tier of the most similar cached prompt when the cosine
similarity reaches the threshold. Entries live in a fixed-size ring buffer, so
the oldest is overwritten once the cache is full.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np

from plugins.classifier import Tier


class CacheMode(Enum):
    OFF = "off"  # no embedding, cache or judge
    SHADOW = "shadow"  # cache and judge run and log; rules still decide
    ACTIVE = "active"  # cache hits decide the tier


@dataclass(frozen=True)
class CacheHit:
    tier: Tier
    similarity: float


class Embedder(Protocol):
    async def embed(self, text: str) -> np.ndarray: ...


class Judge(Protocol):
    async def judge(self, text: str) -> Tier | None: ...


def _normalized(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


class SemanticCache:
    def __init__(self, dimensions: int, threshold: float, max_entries: int) -> None:
        self.threshold = threshold
        self._vectors = np.zeros((max_entries, dimensions), dtype=np.float32)
        self._tiers: list[Tier | None] = [None] * max_entries
        self._count = 0
        self._next = 0
        self._pending: set[str] = set()

    def __len__(self) -> int:
        return self._count

    def lookup(self, vector: np.ndarray) -> CacheHit | None:
        if self._count == 0:
            return None
        similarities = self._vectors[: self._count] @ _normalized(vector)
        best = int(similarities.argmax())
        tier = self._tiers[best]
        if tier is None or similarities[best] < self.threshold:
            return None
        return CacheHit(tier=tier, similarity=float(similarities[best]))

    def add(self, vector: np.ndarray, tier: Tier) -> None:
        self._vectors[self._next] = _normalized(vector)
        self._tiers[self._next] = tier
        self._next = (self._next + 1) % len(self._tiers)
        self._count = min(self._count + 1, len(self._tiers))

    def claim(self, key: str) -> bool:
        """Mark a prompt as being judged; False if it already is."""
        if key in self._pending:
            return False
        self._pending.add(key)
        return True

    def release(self, key: str) -> None:
        self._pending.discard(key)


@dataclass
class SemanticRouting:
    embedder: Embedder
    cache: SemanticCache
    judge: Judge
    mode: CacheMode
