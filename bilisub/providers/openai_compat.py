from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx


class OpenAICompatClient:
    """Client for OpenAI-compatible endpoints (OpenAI, Azure, vLLM, etc.)."""

    def __init__(self, base_url: str, api_key: Optional[str]) -> None:
        self.base_url = base_url.rstrip("/")
        # Respect common env vars if not provided
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._headers = {"Content-Type": "application/json"}
        if self.api_key:
            self._headers["Authorization"] = f"Bearer {self.api_key}"

    def chat(self, messages: List[Dict[str, Any]], model: str, temperature: float = 0.2,
             max_tokens: Optional[int] = None) -> str:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        with httpx.Client(timeout=60) as client:
            resp = client.post(url, headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]
