from __future__ import annotations

from typing import Any, Dict, List


class MockClient:
    def chat(self, messages: List[Dict[str, Any]], model: str, temperature: float = 0.0,
             max_tokens: int | None = None) -> str:
        # Returns a deterministic short response for testing
        last = messages[-1]
        if isinstance(last.get("content"), list):
            return "{\n  \"scene_title\": \"示例画面\",\n  \"text_on_screen\": [\"DEMO\"],\n  \"objects\": [\"screen\", \"text\"],\n  \"actions\": [],\n  \"notes\": \"这是一个用于离线测试的固定返回。\"\n}"
        return "{\n  \"title\": \"示例视频\",\n  \"final_summary\": \"这是一个Mock总结，用于验证管线连通性。\"\n}"
