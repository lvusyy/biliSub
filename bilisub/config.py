from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ProviderKind(str, Enum):
    openrouter = "openrouter"
    openai = "openai"           # 直连 OpenAI 或 兼容API
    vllm = "vllm"               # 本地/服务器 OpenAI 兼容
    ollama = "ollama"           # 本地 Ollama
    mock = "mock"               # 本地假模型，便于离线测试


class ProviderConfig(BaseModel):
    kind: ProviderKind
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class PipelineConfig(BaseModel):
    provider: ProviderKind = ProviderKind.openrouter
    vlm_model: str = "qwen2.5-vl-7b-instruct"
    llm_model: str = "qwen2.5-7b-instruct"
    base_url: Optional[str] = None
    api_key: Optional[str] = None

    def provider_config(self) -> ProviderConfig:
        return ProviderConfig(kind=self.provider, base_url=self.base_url, api_key=self.api_key)
