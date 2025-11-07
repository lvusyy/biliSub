from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import PipelineConfig, ProviderKind
from .frames import sample_frames
from .providers.base import build_provider
from .strategy import decide_strategy
from .summarize import summarize_video
from .vlm import parse_frames_with_vlm


def run_pipeline(
    *,
    video_path: Optional[str],
    subs_path: str,
    provider: ProviderKind | str = ProviderKind.openrouter,
    vlm_model: str = "qwen2.5-vl-7b-instruct",
    llm_model: str = "qwen2.5-7b-instruct",
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    language: str = "auto",
    max_frames: int = 40,
    dry_run: bool = False,
) -> Dict[str, Any]:
    if isinstance(provider, str):
        provider = ProviderKind(provider)

    subs_text = Path(subs_path).read_text(encoding="utf-8", errors="ignore")
    strategy = decide_strategy(subs_text, preferred_lang=language)

    frames: List = []
    if not dry_run:
        if not video_path:
            raise ValueError("非 dry-run 模式下必须提供 video_path")
        frames = sample_frames(
            video_path,
            frames_per_min=strategy.frames_per_min,
            max_frames=min(max_frames, strategy.max_frames),
        )

    provider_client = build_provider(
        PipelineConfig(
            provider=provider,
            vlm_model=vlm_model,
            llm_model=llm_model,
            base_url=base_url,
            api_key=api_key,
        )
    )

    visual_notes = parse_frames_with_vlm(
        provider=provider_client,
        model=vlm_model,
        frames=frames,
        strategy=strategy,
        dry_run=dry_run,
    )

    result = summarize_video(
        provider=provider_client,
        model=llm_model,
        subtitles_text=subs_text,
        visual_notes=visual_notes,
        language=strategy.language,
    )
    return {
        "strategy": {
            "kind": strategy.kind,
            "frames_per_min": strategy.frames_per_min,
            "max_frames": strategy.max_frames,
            "vlm_prompt_style": strategy.vlm_prompt_style,
            "language": strategy.language,
        },
        "summary": result,
        "visual_notes": visual_notes,
    }
