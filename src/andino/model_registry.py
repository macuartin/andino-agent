from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_model(provider: str, model_id: str, *, max_tokens: int = 4096) -> Any:
    """Build a Strands model object for the given provider."""
    provider = provider.strip().lower()

    if provider == "bedrock":
        return _build_bedrock(model_id, max_tokens)
    if provider == "anthropic":
        return _build_anthropic(model_id, max_tokens)
    if provider == "openai":
        return _build_openai(model_id)

    raise ValueError(f"Unsupported model provider: {provider}")


def _build_bedrock(model_id: str, max_tokens: int) -> Any:
    import os

    from strands.models import BedrockModel

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    kwargs: dict[str, Any] = {"model_id": model_id, "max_tokens": max_tokens}
    if region:
        kwargs["region_name"] = region
    return BedrockModel(**kwargs)


def _build_anthropic(model_id: str, max_tokens: int) -> Any:
    from strands.models import AnthropicModel

    return AnthropicModel(model_id=model_id, max_tokens=max_tokens)


def _build_openai(model_id: str) -> Any:
    from strands.models import OpenAIModel

    return OpenAIModel(model_id=model_id)
