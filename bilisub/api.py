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
from .cache import load_latest, load_by_profile, save_result
from . import __version__ as PIPELINE_VERSION


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
    bv_id: Optional[str] = None,
) -> Dict[str, Any]:
    if isinstance(provider, str):
        provider = ProviderKind(provider)

    # 0) Cache quick path by BV only
    if bv_id:
        cached = load_latest(bv_id)
        if cached and isinstance(cached, dict) and "data" in cached:
            out = cached["data"]
            # 标注缓存命中
            out.setdefault("meta", {})
            out["meta"].update({"cache_hit": True, "cache_bv": bv_id, "pipeline_version": PIPELINE_VERSION})
            return out

    subs_text = Path(subs_path).read_text(encoding="utf-8", errors="ignore")
    strategy = decide_strategy(subs_text, preferred_lang=language)

    # profile 用于更精确命中（不同配置可能产生不同结果）
    profile = {
        "pipeline_version": PIPELINE_VERSION,
        "provider": str(provider),
        "vlm_model": vlm_model,
        "llm_model": llm_model,
        "language": language,
        "strategy": {
            "kind": strategy.kind,
            "vlm_prompt_style": strategy.vlm_prompt_style,
            "frames_per_min": strategy.frames_per_min,
            "max_frames": min(max_frames, strategy.max_frames),
        },
    }

    if bv_id:
        precise = load_by_profile(bv_id, profile)
        if precise and isinstance(precise, dict) and "data" in precise:
            out = precise["data"]
            out.setdefault("meta", {})
            out["meta"].update({"cache_hit": True, "cache_bv": bv_id, "pipeline_version": PIPELINE_VERSION})
            return out

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
    payload = {
        "strategy": {
            "kind": strategy.kind,
            "frames_per_min": strategy.frames_per_min,
            "max_frames": strategy.max_frames,
            "vlm_prompt_style": strategy.vlm_prompt_style,
            "language": strategy.language,
        },
        "summary": result,
        "visual_notes": visual_notes,
        "meta": {"cache_hit": False, "pipeline_version": PIPELINE_VERSION},
    }

    if bv_id:
        save_result(bv_id, profile, payload)

    return payload
