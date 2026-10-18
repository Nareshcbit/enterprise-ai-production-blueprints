"""Local CPU text embeddings with fastembed (ONNX, no GPU, no network call)."""

import asyncio

import numpy as np
from fastembed import TextEmbedding

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384


class FastEmbedEmbedder:
    """Loads the model on first use, so importing the plugin stays cheap."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model: TextEmbedding | None = None

    def _embed_sync(self, text: str) -> np.ndarray:
        if self._model is None:
            self._model = TextEmbedding(self.model_name)
        return next(iter(self._model.embed([text])))

    async def embed(self, text: str) -> np.ndarray:
        # CPU-bound: run off the event loop so other requests keep flowing.
        return await asyncio.to_thread(self._embed_sync, text)
