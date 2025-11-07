from __future__ import annotations

import base64
from typing import Any, Dict, List

import httpx


class OllamaClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: List[Dict[str, Any]], model: str, temperature: float = 0.2,
             max_tokens: int | None = None) -> str:
        # Convert OpenAI-style messages to Ollama chat format
        ollama_messages: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content")
            # content could be str or list[dict]
            images_b64: List[str] = []
            text_parts: List[str] = []
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url") if isinstance(part.get("image_url"), dict) else part.get("image_url")
                        if isinstance(url, str) and url.startswith("data:image"):
                            b64 = url.split(",", 1)[-1]
                            images_b64.append(b64)
                        else:
                            # If URL (not base64), fetch and convert
                            if isinstance(url, str):
                                with httpx.Client(timeout=30) as client:
                                    resp = client.get(url)
                                    resp.raise_for_status()
                                    images_b64.append(base64.b64encode(resp.content).decode("utf-8"))
            ollama_messages.append({
                "role": role,
                "content": "\n".join(text_parts).strip(),
                **({"images": images_b64} if images_b64 else {}),
            })

        payload: Dict[str, Any] = {
            "model": model,
            "messages": ollama_messages,
            "options": {"temperature": temperature},
            "stream": False,
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        url = f"{self.base_url}/api/chat"
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data.get("message", {}).get("content", "")
