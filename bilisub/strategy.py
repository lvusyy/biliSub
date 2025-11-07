from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


auto = "auto"


@dataclass
class Strategy:
    kind: Literal["tutorial", "slides", "game", "talk", "vlog", "movie", "unknown"]
    sampling: Literal["uniform", "scene"]
    frames_per_min: int
    max_frames: int
    vlm_prompt_style: Literal["slide_extractor", "ui_extractor", "scene_descriptor", "generic"]
    language: Literal["zh", "en"]


def _detect_language(text: str, preferred: str = auto) -> str:
    if preferred in ("zh", "en"):
        return preferred
    # crude heuristic: ratio of CJK characters
    cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    return "zh" if cjk > 50 else "en"


def decide_strategy(subtitles_text: str, preferred_lang: str = auto) -> Strategy:
    text = subtitles_text.lower()
    lang = _detect_language(subtitles_text, preferred_lang)

    def any_kw(words: list[str]) -> bool:
        return any(w in text for w in words)

    # Heuristics
    if any_kw(["教程", "步骤", "安装", "点击", "配置", "chapter", "lesson", "slide", "ppt", "目录"]):
        return Strategy("tutorial", "uniform", frames_per_min=12, max_frames=80,
                        vlm_prompt_style="slide_extractor", language=lang)
    if any_kw(["ppt", "幻灯片", "slide", "presentation"]):
        return Strategy("slides", "uniform", frames_per_min=10, max_frames=70,
                        vlm_prompt_style="slide_extractor", language=lang)
    if any_kw(["游戏", "击杀", "排位", "live", "match", "gameplay"]):
        return Strategy("game", "uniform", frames_per_min=20, max_frames=120,
                        vlm_prompt_style="ui_extractor", language=lang)
    if any_kw(["演讲", "访谈", "播客", "talk", "podcast", "interview"]):
        return Strategy("talk", "uniform", frames_per_min=6, max_frames=60,
                        vlm_prompt_style="scene_descriptor", language=lang)
    if any_kw(["vlog", "旅行", "日常", "记录"]):
        return Strategy("vlog", "uniform", frames_per_min=8, max_frames=80,
                        vlm_prompt_style="scene_descriptor", language=lang)
    if any_kw(["电影", "剧情", "片段", "movie", "scene"]):
        return Strategy("movie", "uniform", frames_per_min=15, max_frames=100,
                        vlm_prompt_style="scene_descriptor", language=lang)

    return Strategy("unknown", "uniform", frames_per_min=10, max_frames=80,
                    vlm_prompt_style="generic", language=lang)
