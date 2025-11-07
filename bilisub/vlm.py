from __future__ import annotations

import base64
import io
import json
from typing import Any, Dict, List

from PIL import Image
import time
from tenacity import retry, stop_after_attempt, wait_exponential

from .providers.base import ProviderClient
from .strategy import Strategy


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def _chat_with_retry(provider: ProviderClient, messages, model: str):
    return provider.chat(messages=messages, model=model)


def _pil_to_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _build_vlm_prompt(style: str, language: str) -> str:
    if language == "zh":
        if style == "slide_extractor":
            return (
                "你是PPT/教程画面解析助手。请从图片中提取: 1) 标题/小标题 2) 关键要点(尽量有层级) 3) 重要术语 4) 公式/代码 5) 屏幕文字。"
                "以JSON输出，字段: scene_title, bullet_points[], text_on_screen[], code_or_formula[], notes。"
            )
        if style == "ui_extractor":
            return (
                "你是游戏/应用UI解析助手。请从图片中提取: 1) 画面主要元素 2) UI状态(血量/分数/时间等) 3) 发生的行动 4) 屏幕文字。"
                "以JSON输出，字段: scene_title, objects[], ui_state{...}, actions[], text_on_screen[], notes。"
            )
        if style == "scene_descriptor":
            return (
                "你是视频画面描述助手。请简要描述场景、人物/物体、动作以及关键信息。"
                "以JSON输出，字段: scene_title, description, key_entities[], actions[], text_on_screen[], notes。"
            )
        return (
            "从图片中提取关键信息，以JSON输出: scene_title, description, text_on_screen[], objects[], notes。"
        )
    else:
        if style == "slide_extractor":
            return (
                "You are a slide/tutorial parser. Extract: 1) title/subtitles 2) key bullet points 3) important terms"
                " 4) formulas/code 5) on-screen text. Output JSON with: scene_title, bullet_points[], text_on_screen[],"
                " code_or_formula[], notes."
            )
        if style == "ui_extractor":
            return (
                "You are a UI/gameplay parser. Extract: 1) main elements 2) UI state (HP/score/time etc.) 3) actions"
                " 4) on-screen text. Output JSON: scene_title, objects[], ui_state{...}, actions[], text_on_screen[], notes."
            )
        if style == "scene_descriptor":
            return (
                "You are a scene describer. Summarize scene, entities, actions, and key details. Output JSON:"
                " scene_title, description, key_entities[], actions[], text_on_screen[], notes."
            )
        return (
            "Extract key info from the image. Output JSON: scene_title, description, text_on_screen[], objects[], notes."
        )


def parse_frames_with_vlm(provider: ProviderClient, model: str, frames: List[Image.Image],
                           strategy: Strategy, dry_run: bool = False, req_interval: float = 0.0) -> List[Dict[str, Any]]:
    prompt = _build_vlm_prompt(strategy.vlm_prompt_style, strategy.language)
    results: List[Dict[str, Any]] = []

    if dry_run:
        # send a single mock image-free prompt to provider to validate path
        content = [{"type": "text", "text": prompt}]
        text = _chat_with_retry(provider, messages=[{"role": "user", "content": content}], model=model)
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {"notes": text}
        results.append(parsed)
        return results

    for img in frames:
        data_url = _pil_to_data_url(img)
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        text = _chat_with_retry(provider, messages=[{"role": "user", "content": content}], model=model)
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = {"raw": text}
        results.append(parsed)
        if req_interval > 0:
            time.sleep(req_interval)

    return results
