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
    source_url: Optional[str] = None,
    cache_readonly: bool = False,
    refresh_cache: bool = False,
    cache_root: Optional[str] = None,
    save_frames_dir: Optional[str] = None,
    vlm_req_interval: float = 0.0,
) -> Dict[str, Any]:
    if isinstance(provider, str):
        provider = ProviderKind(provider)

    # 0) Resolve BV from inputs
    from .utils import extract_bv_id, derive_bv_from_paths
    effective_bv = bv_id or (extract_bv_id(source_url) if source_url else None) or derive_bv_from_paths(subs_path, video_path)

    # 1) Cache quick path by BV only (unless refresh requested)
    if effective_bv and not refresh_cache:
        cached = load_latest(effective_bv, root=Path(cache_root) if cache_root else None or None)
        if cached and isinstance(cached, dict) and "data" in cached:
            out = cached["data"]
            out.setdefault("meta", {})
            out["meta"].update({"cache_hit": True, "cache_bv": effective_bv, "pipeline_version": PIPELINE_VERSION})
            return out

    subs_text = Path(subs_path).read_text(encoding="utf-8", errors="ignore")
    strategy = decide_strategy(subs_text, preferred_lang=language)

    # profile 用于更精确命中（不同配置可能产生不同结果）
    effective_max = min(max_frames, strategy.max_frames)
    profile = {
        "pipeline_version": PIPELINE_VERSION,
        "provider": provider.value,
        "vlm_model": vlm_model,
        "llm_model": llm_model,
        "language": language,
        "strategy": {
            "kind": strategy.kind,
            "sampling": getattr(strategy, "sampling", "uniform"),
            "vlm_prompt_style": strategy.vlm_prompt_style,
            "frames_per_min": strategy.frames_per_min,
            "max_frames": effective_max,
        },
    }

    if effective_bv and not refresh_cache:
        precise = load_by_profile(effective_bv, profile, root=Path(cache_root) if cache_root else None or None)
        if precise and isinstance(precise, dict) and "data" in precise:
            out = precise["data"]
            out.setdefault("meta", {})
            out["meta"].update({"cache_hit": True, "cache_bv": effective_bv, "pipeline_version": PIPELINE_VERSION})
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
        req_interval=vlm_req_interval,
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
            "sampling": getattr(strategy, "sampling", "uniform"),
            "frames_per_min": strategy.frames_per_min,
            "max_frames": effective_max,
            "vlm_prompt_style": strategy.vlm_prompt_style,
            "language": strategy.language,
        },
        "summary": result,
        "visual_notes": visual_notes,
        "meta": {"cache_hit": False, "pipeline_version": PIPELINE_VERSION, "cache_bv": effective_bv},
    }

    # Save frames if requested
    if save_frames_dir and frames:
        outdir = Path(save_frames_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        for i, img in enumerate(frames):
            img.save(outdir / f"frame_{i:04d}.jpg", format="JPEG", quality=85)

    if effective_bv and not cache_readonly:
        save_result(effective_bv, profile, payload, root=Path(cache_root) if cache_root else None or None)

    return payload
