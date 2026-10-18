import numpy as np

from plugins.classifier import Tier
from plugins.semantic_cache import SemanticCache


def _vector(*values: float) -> np.ndarray:
    return np.array(values, dtype=np.float32)


def _cache(max_entries: int = 10) -> SemanticCache:
    return SemanticCache(dimensions=3, threshold=0.9, max_entries=max_entries)


def test_empty_cache_misses() -> None:
    assert _cache().lookup(_vector(1, 0, 0)) is None


def test_exact_match_hits_with_similarity_one() -> None:
    cache = _cache()
    cache.add(_vector(1, 0, 0), Tier.COMPLEX)
    hit = cache.lookup(_vector(1, 0, 0))
    assert hit is not None
    assert hit.tier is Tier.COMPLEX
    assert round(hit.similarity, 6) == 1.0


def test_similarity_ignores_vector_length() -> None:
    cache = _cache()
    cache.add(_vector(2, 0, 0), Tier.STANDARD)
    hit = cache.lookup(_vector(0.5, 0, 0))
    assert hit is not None
    assert round(hit.similarity, 6) == 1.0


def test_near_match_above_threshold_hits() -> None:
    cache = _cache()
    cache.add(_vector(1, 0, 0), Tier.STANDARD)
    hit = cache.lookup(_vector(1, 0.2, 0))  # cosine ~0.98
    assert hit is not None
    assert hit.tier is Tier.STANDARD


def test_match_below_threshold_misses() -> None:
    cache = _cache()
    cache.add(_vector(1, 0, 0), Tier.STANDARD)
    assert cache.lookup(_vector(1, 1, 0)) is None  # cosine ~0.71


def test_lookup_returns_the_closest_entry() -> None:
    cache = _cache()
    cache.add(_vector(1, 0, 0), Tier.STANDARD)
    cache.add(_vector(0, 1, 0), Tier.COMPLEX)
    hit = cache.lookup(_vector(0.1, 1, 0))
    assert hit is not None
    assert hit.tier is Tier.COMPLEX


def test_full_cache_overwrites_the_oldest_entry() -> None:
    cache = _cache(max_entries=2)
    cache.add(_vector(1, 0, 0), Tier.STANDARD)
    cache.add(_vector(0, 1, 0), Tier.STANDARD)
    cache.add(_vector(0, 0, 1), Tier.COMPLEX)
    assert len(cache) == 2
    assert cache.lookup(_vector(1, 0, 0)) is None
    assert cache.lookup(_vector(0, 0, 1)) is not None


def test_claim_blocks_a_second_claim_until_released() -> None:
    cache = _cache()
    assert cache.claim("prompt-hash") is True
    assert cache.claim("prompt-hash") is False
    cache.release("prompt-hash")
    assert cache.claim("prompt-hash") is True
