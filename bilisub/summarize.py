from __future__ import annotations

import json
from typing import Any, Dict, List

from .providers.base import ProviderClient
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def _chat_with_retry(provider: ProviderClient, messages, model: str):
    return provider.chat(messages=messages, model=model)


def _build_summary_prompt(language: str) -> str:
    if language == "zh":
        return (
            "结合提供的字幕片段与画面要点(JSON)，生成对视频的结构化总结。"
            "请输出JSON，包含: title, topics[], timeline[], key_takeaways[], action_items[], final_summary。"
            "注意：不要编造不存在的信息，如不确定可标注 '未知'。"
        )
    else:
        return (
            "Using the provided subtitles and visual notes (JSON), produce a structured summary of the video."
            " Output JSON with: title, topics[], timeline[], key_takeaways[], action_items[], final_summary."
            " Avoid hallucinations; label uncertain parts as 'unknown'."
        )


def summarize_video(provider: ProviderClient, model: str, subtitles_text: str,
                    visual_notes: List[Dict[str, Any]], language: str = "zh") -> Dict[str, Any]:
    # Trim overly long subtitles for token safety (simple heuristic)
    max_chars = 12000
    sub_text = subtitles_text[:max_chars]
    prompt = _build_summary_prompt(language)

    user_content = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": "字幕(截断可能):\n" + sub_text},
        {"type": "text", "text": "画面要点(JSON):\n" + json.dumps(visual_notes, ensure_ascii=False)[:14000]},
    ]

    text = _chat_with_retry(provider, messages=[{"role": "user", "content": user_content}], model=model)
    try:
        return json.loads(text)
    except Exception:
        return {"final_summary": text}
