from __future__ import annotations

from functools import lru_cache
from typing import Any, List

from fastembed import TextEmbedding
from llama_index.core.base.embeddings.base import BaseEmbedding

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=4)
def _load_model(model_name: str) -> TextEmbedding:
    return TextEmbedding(model_name=model_name)


class FastEmbedONNXEmbedding(BaseEmbedding):
    """LlamaIndex-compatible embedding backed by fastembed (ONNXRuntime)."""

    model_name: str = DEFAULT_MODEL_NAME

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, **kwargs: Any) -> None:
        super().__init__(model_name=model_name, **kwargs)

    @classmethod
    def class_name(cls) -> str:
        return "FastEmbedONNXEmbedding"

    def _embed(self, texts: List[str]) -> List[List[float]]:
        model = _load_model(self.model_name)
        return [vec.tolist() for vec in model.embed(texts)]

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._embed([query])[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._embed([text])[0]

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embedding(text)


if __name__ == "__main__":
    embed = FastEmbedONNXEmbedding()  # our class
    print(len(embed.get_query_embedding("test")))  # 384
