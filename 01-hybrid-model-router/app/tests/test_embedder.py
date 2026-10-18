import os

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="loads the real embedding model; set RUN_INTEGRATION=1",
)


async def test_real_model_returns_normalized_384_dim_vectors() -> None:
    from plugins.embedder import DIMENSIONS, FastEmbedEmbedder

    vector = await FastEmbedEmbedder().embed("Extract the invoice number.")
    assert vector.shape == (DIMENSIONS,)
    assert abs(float(np.linalg.norm(vector)) - 1.0) < 1e-3


async def test_similar_prompts_score_higher_than_unrelated_ones() -> None:
    from plugins.embedder import FastEmbedEmbedder

    embedder = FastEmbedEmbedder()
    invoice_a = await embedder.embed("Extract the invoice number from INV-4471.")
    invoice_b = await embedder.embed("Extract the invoice number from INV-9902.")
    contract = await embedder.embed("Compare the liability clauses in these contracts.")
    assert float(invoice_a @ invoice_b) > float(invoice_a @ contract)
