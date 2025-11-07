from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional

import httpx

from ..config import ProviderConfig, ProviderKind


class ProviderClient:
    def chat(self, messages: List[Dict[str, Any]], model: str, temperature: float = 0.2,
             max_tokens: Optional[int] = None) -> str:
        raise NotImplementedError


def build_provider(cfg: 'PipelineConfig | ProviderConfig') -> ProviderClient:
    # allow both PipelineConfig and ProviderConfig
    if hasattr(cfg, 'provider'):
        kind = getattr(cfg, 'provider')  # PipelineConfig
        base_url = getattr(cfg, 'base_url', None)
        api_key = getattr(cfg, 'api_key', None)
    else:
        kind = cfg.kind
        base_url = cfg.base_url
        api_key = cfg.api_key

    if kind == ProviderKind.openrouter:
        from .openrouter import OpenRouterClient
        return OpenRouterClient(base_url or "https://openrouter.ai/api/v1", api_key)
    if kind in (ProviderKind.openai, ProviderKind.vllm):
        from .openai_compat import OpenAICompatClient
        return OpenAICompatClient(base_url or "http://localhost:8000/v1", api_key)
    if kind == ProviderKind.ollama:
        from .ollama import OllamaClient
        return OllamaClient(base_url or "http://localhost:11434")
    if kind == ProviderKind.mock:
        from .mock import MockClient
        return MockClient()
    raise ValueError(f"Unknown provider kind: {kind}")
