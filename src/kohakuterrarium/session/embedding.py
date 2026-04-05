"""
Embedding providers for session memory search.

Three tiers:
  - Model2Vec (default): ~8 MB, numpy-only, microsecond inference
  - SentenceTransformer: Gemma/Jina/any HF model, optional dep
  - API: OpenAI, Google, Jina via HTTP
"""

import os
from abc import ABC, abstractmethod
from typing import Any

import httpx
import numpy as np

from kohakuterrarium.utils.logging import get_logger

logger = get_logger(__name__)


class BaseEmbedder(ABC):
    """Abstract embedding provider."""

    dimensions: int = 0

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts into embedding vectors.

        Args:
            texts: List of text strings to embed

        Returns:
            numpy array of shape (len(texts), dimensions), dtype float32
        """
        ...

    def encode_one(self, text: str) -> np.ndarray:
        """Encode a single text. Returns 1D vector."""
        return self.encode([text])[0]


class Model2VecEmbedder(BaseEmbedder):
    """Model2Vec static embeddings (default, CPU-only, microsecond speed).

    Uses potion-base-8M (~8 MB) or potion-retrieval-32M (~32 MB).
    Dependencies: model2vec (pip install model2vec)
    """

    def __init__(self, model_name: str = "minishlab/potion-base-8M"):
        try:
            from model2vec import StaticModel
        except ImportError:
            raise ImportError(
                "model2vec is required for Model2Vec embeddings. "
                "Install: pip install model2vec"
            )

        logger.info("Loading Model2Vec", model=model_name)
        self._model = StaticModel.from_pretrained(model_name)
        self.dimensions = self._model.dim
        logger.info("Model2Vec loaded", model=model_name, dimensions=self.dimensions)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._model.encode(texts).astype(np.float32)


class SentenceTransformerEmbedder(BaseEmbedder):
    """SentenceTransformer embeddings (Gemma, Jina, bge, etc.).

    Dependencies: sentence-transformers (pip install sentence-transformers)
    Optional ONNX: pip install sentence-transformers[onnx]
    """

    def __init__(
        self,
        model_name: str = "google/embeddinggemma-300m",
        dimensions: int | None = None,
        device: str = "cpu",
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required. "
                "Install: pip install sentence-transformers"
            )

        logger.info("Loading SentenceTransformer", model=model_name)
        # Jina v5 requires default_task; other models ignore it
        self._model = SentenceTransformer(
            model_name,
            device=device,
            trust_remote_code=True,
            model_kwargs={"default_task": "retrieval"},
        )
        self._truncate_dim = dimensions
        # Detect dimensions (some models return None from the accessor)
        auto_dim = self._model.get_sentence_embedding_dimension()
        if auto_dim is None:
            probe = self._model.encode(["test"])
            auto_dim = probe.shape[1]
        self.dimensions = dimensions or auto_dim
        logger.info(
            "SentenceTransformer loaded",
            model=model_name,
            dimensions=self.dimensions,
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        if self._truncate_dim and vecs.shape[1] > self._truncate_dim:
            vecs = vecs[:, : self._truncate_dim]
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1
            vecs = vecs / norms
        return vecs.astype(np.float32)


class APIEmbedder(BaseEmbedder):
    """API-based embeddings (OpenAI, Google, Jina).

    Uses the OpenAI-compatible /v1/embeddings endpoint.
    Works with OpenAI, Google (via OpenAI compat), Jina, etc.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: str = "https://api.openai.com/v1",
        dimensions: int | None = None,
    ):
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self._model = model
        self.dimensions = dimensions or 1536
        self._request_dims = dimensions

    def encode(self, texts: list[str]) -> np.ndarray:
        body: dict[str, Any] = {
            "input": texts,
            "model": self._model,
        }
        if self._request_dims:
            body["dimensions"] = self._request_dims

        resp = self._client.post("/embeddings", json=body)
        resp.raise_for_status()
        data = resp.json()

        vecs = []
        for item in sorted(data["data"], key=lambda x: x["index"]):
            vecs.append(item["embedding"])

        result = np.array(vecs, dtype=np.float32)
        if self.dimensions == 0:
            self.dimensions = result.shape[1]
        return result


class NullEmbedder(BaseEmbedder):
    """No-op embedder for sessions without embedding config.

    Only FTS keyword search is available.
    """

    dimensions = 0

    def encode(self, texts: list[str]) -> np.ndarray:
        raise RuntimeError(
            "No embedding model configured. "
            "Use keyword search (mode='fts') or configure an embedding provider."
        )


# ── Model presets ────────────────────────────────────────────────────
# Use via config: { provider: model2vec, model: "@retrieval" }
# or just:        { provider: model2vec, model: "minishlab/potion-retrieval-32M" }

MODEL2VEC_PRESETS: dict[str, dict[str, Any]] = {
    # Tiny (< 10M params, pure numpy, microsecond inference)
    "tiny": {"model": "minishlab/potion-base-2M"},  # 64-dim, ~2MB
    "base": {"model": "minishlab/potion-base-8M"},  # 256-dim, ~8MB
    # Retrieval-optimized
    "retrieval": {"model": "minishlab/potion-retrieval-32M"},  # 512-dim, ~32MB
    # High-quality static (Matryoshka 1024/512/256/128/64/32)
    "best": {
        "model": "sentence-transformers/static-retrieval-mrl-en-v1",  # 1024-dim, ~120MB
    },
    # Multilingual
    "multilingual": {
        "model": "minishlab/potion-multilingual-128M",  # 256-dim, 101 langs, ~512MB
    },
    "multilingual-best": {
        "model": "sentence-transformers/static-similarity-mrl-multilingual-v1",  # 1024-dim, 51 langs
    },
    # Science domain
    "science": {"model": "minishlab/potion-science-32M"},  # 256-dim, arxiv+pubmed
}

ST_PRESETS: dict[str, dict[str, Any]] = {
    # Tiny (< 50M params)
    "tiny": {
        "model": "ibm-granite/granite-embedding-30m-english",  # 384-dim, 512 ctx
    },
    "small": {
        "model": "ibm-granite/granite-embedding-small-english-r2",  # 384-dim, 8K ctx
    },
    # Base (100-150M params)
    "base": {
        "model": "Alibaba-NLP/gte-modernbert-base",  # 768-dim, 8K ctx, BEIR 55.33
    },
    "nomic": {
        "model": "nomic-ai/nomic-embed-text-v1.5",  # 768-dim, 8K ctx, Matryoshka
    },
    # Medium (300M+ params)
    "gemma": {
        "model": "google/embeddinggemma-300m",  # 768-dim, 2K ctx, 100+ langs
    },
    "multilingual": {
        "model": "Alibaba-NLP/gte-multilingual-base",  # 768-dim, 8K ctx, 70+ langs
    },
}

DEFAULT_M2V_MODEL = "minishlab/potion-retrieval-32M"
DEFAULT_ST_MODEL = "Alibaba-NLP/gte-modernbert-base"


def _resolve_preset(
    model: str, presets: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """Resolve a @preset reference to a preset dict, or None."""
    if model.startswith("@"):
        name = model[1:]
        if name in presets:
            return presets[name]
        logger.warning("Unknown embedding preset", preset=name)
    return None


def _detect_best_provider() -> str:
    """Detect the best available embedding provider.

    Preference: model2vec (lightweight default) > sentence-transformers > none.
    """
    try:
        import model2vec  # noqa: F401

        return "model2vec"
    except ImportError:
        pass
    try:
        import sentence_transformers  # noqa: F401

        return "sentence-transformer"
    except ImportError:
        pass
    return "none"


def list_embedding_presets() -> dict[str, dict[str, dict[str, Any]]]:
    """Return all available presets grouped by provider."""
    return {"model2vec": MODEL2VEC_PRESETS, "sentence-transformer": ST_PRESETS}


def create_embedder(config: dict[str, Any] | None = None) -> BaseEmbedder:
    """Create an embedder from config dict.

    Config format::

        provider: "auto" | "model2vec" | "sentence-transformer" | "api" | "none"
        model: model name, HuggingFace path, or "@preset" (e.g. "@retrieval")
        dimensions: optional dimension override (Matryoshka truncation)
        api_key: for API providers
        base_url: for API providers
        device: "cpu" or "cuda" (for sentence-transformer)

    Preset examples::

        { provider: model2vec, model: "@retrieval" }     # potion-retrieval-32M
        { provider: model2vec, model: "@multilingual" }   # potion-multilingual-128M
        { provider: sentence-transformer, model: "@base" } # gte-modernbert-base
        { provider: sentence-transformer, model: "@gemma" } # embeddinggemma-300m

    "auto" (default): tries model2vec first, falls back to
    sentence-transformers, then NullEmbedder.

    Returns NullEmbedder if config is None or provider is "none".
    """
    if not config:
        return NullEmbedder()

    provider = config.get("provider", "auto")

    if provider == "auto":
        provider = _detect_best_provider()

    match provider:
        case "model2vec":
            model = config.get("model", DEFAULT_M2V_MODEL)
            preset = _resolve_preset(model, MODEL2VEC_PRESETS)
            if preset:
                model = preset["model"]
            return Model2VecEmbedder(model_name=model)

        case "sentence-transformer":
            model = config.get("model", DEFAULT_ST_MODEL)
            dims = config.get("dimensions")
            device = config.get("device", "cpu")
            preset = _resolve_preset(model, ST_PRESETS)
            if preset:
                model = preset["model"]
                dims = dims or preset.get("dimensions")
            return SentenceTransformerEmbedder(
                model_name=model, dimensions=dims, device=device
            )

        case "api":
            api_key = config.get("api_key", "")
            if not api_key:
                api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
                api_key = os.environ.get(api_key_env, "")
            if not api_key:
                raise ValueError("API embedding requires api_key or api_key_env")
            return APIEmbedder(
                api_key=api_key,
                model=config.get("model", "text-embedding-3-small"),
                base_url=config.get("base_url", "https://api.openai.com/v1"),
                dimensions=config.get("dimensions"),
            )

        case "none":
            return NullEmbedder()

        case _:
            logger.warning("Unknown embedding provider, using none", provider=provider)
            return NullEmbedder()
