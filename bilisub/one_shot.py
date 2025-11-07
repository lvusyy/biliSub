from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

from .utils import extract_bv_id, find_latest_subs


def _run(cmd: list[str], cwd: Optional[str] = None) -> None:
    subprocess.run(cmd, check=True, cwd=cwd)


def download_video(url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Use yt-dlp to download and merge to mp4 when possible
    # Output template includes video id for uniqueness
    output_tpl = str(out_dir / "%(title)s-%(id)s.%(ext)s")
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", output_tpl,
        url,
    ]
    _run(cmd)
    # Pick the newest video file in directory
    candidates = []
    for ext in [".mp4", ".mkv", ".webm", ".flv", ".mov"]:
        candidates.extend(out_dir.glob(f"*{ext}"))
    if not candidates:
        raise RuntimeError("未找到下载的视频文件。请确认 yt-dlp 可用，且目标视频允许下载。")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def download_subtitles(url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Leverage existing V1 downloader to fetch subtitles
    cmd = [sys.executable, "enhanced_bilisub.py", "-i", url, "-o", str(out_dir)]
    _run(cmd)
    subs = find_latest_subs(out_dir)
    if not subs:
        raise RuntimeError("未在字幕输出目录找到字幕文件。")
    return subs


def run_one_shot(
    *,
    url: str,
    provider: str = "openrouter",
    vlm_model: str = "qwen3-vl",
    llm_model: str = "qwen2.5-7b-instruct",
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    language: str = "auto",
    max_frames: int = 40,
    refresh_cache: bool = False,
    cache_readonly: bool = False,
    vlm_req_interval: float = 0.0,
    save_frames_dir: Optional[str] = None,
) -> dict:
    bv = extract_bv_id(url) or "anon"
    job_dir = Path("output") / "jobs" / bv
    vid_dir = job_dir / "video"
    sub_dir = job_dir / "subs"

    video_path = download_video(url, vid_dir)
    subs_path = download_subtitles(url, sub_dir)

    from .api import run_pipeline
    result = run_pipeline(
        video_path=str(video_path),
        subs_path=str(subs_path),
        provider=provider,
        vlm_model=vlm_model,
        llm_model=llm_model,
        base_url=base_url,
        api_key=api_key,
        language=language,
        max_frames=max_frames,
        dry_run=False,
        bv_id=bv,
        source_url=url,
        cache_readonly=cache_readonly,
        refresh_cache=refresh_cache,
        save_frames_dir=save_frames_dir,
        vlm_req_interval=vlm_req_interval,
    )
    return result
