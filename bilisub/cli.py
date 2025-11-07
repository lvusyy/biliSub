from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional

from rich import print as rprint
from rich.console import Console
from rich.table import Table

from .config import PipelineConfig, ProviderKind
from .strategy import decide_strategy
from .frames import sample_frames
from .vlm import parse_frames_with_vlm
from .summarize import summarize_video
from .providers.base import build_provider

console = Console()


def _read_subtitles_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="bilisub-v2",
        description="BiliSub V2: 基于字幕自适应选择视觉解析策略，并结合字幕+画面做视频核心要点总结",
    )
    parser.add_argument("--video", type=str, help="视频文件路径 (mp4/mkv 等)")
    parser.add_argument("--subs", type=str, help="字幕文件路径 (srt/ass/vtt/txt/json)")

    parser.add_argument("--provider", type=str, default="openrouter",
                        choices=[p.value for p in ProviderKind], help="推理提供方")
    parser.add_argument("--vlm-model", type=str, default="qwen2.5-vl-7b-instruct",
                        help="视觉-语言模型名称")
    parser.add_argument("--llm-model", type=str, default="qwen2.5-7b-instruct",
                        help="文本总结模型名称")

    parser.add_argument("--base-url", type=str, default=None,
                        help="OpenAI兼容/自建/vLLM/Ollama 的 Base URL")
    parser.add_argument("--api-key-env", type=str, default=None,
                        help="从该环境变量读取API Key；OpenRouter默认为 OPENROUTER_API_KEY")

    parser.add_argument("--max-frames", type=int, default=40, help="最多采样的帧数上限")
    parser.add_argument("--out", type=str, default="output/v2_summary.json", help="输出JSON路径")
    parser.add_argument("--language", type=str, default="auto", help="总结语言，auto/zh/en")
    parser.add_argument("--dry-run", action="store_true", help="不读取视频文件，使用Mock Provider做演示")

    args = parser.parse_args(argv)

    cfg = PipelineConfig(
        provider=ProviderKind(args.provider),
        vlm_model=args.vlm_model,
        llm_model=args.llm_model,
        base_url=args.base_url,
        api_key=os.environ.get(args.api_key_env) if args.api_key_env else None,
    )

    subs_path = Path(args.subs)
    if not subs_path.exists():
        raise SystemExit(f"字幕文件不存在: {subs_path}")

    subs_text = _read_subtitles_text(subs_path)

    # 1) 决策解析策略
    strategy = decide_strategy(subs_text, preferred_lang=args.language)

    table = Table(title="解析策略")
    table.add_column("维度")
    table.add_column("值")
    table.add_row("内容类型", strategy.kind)
    table.add_row("采样方式", strategy.sampling)
    table.add_row("每分钟帧数", str(strategy.frames_per_min))
    table.add_row("最大帧数", str(min(args.max_frames, strategy.max_frames)))
    table.add_row("VLM提示风格", strategy.vlm_prompt_style)
    console.print(table)

    frames = []
    if args.dry_run:
        rprint("[yellow]Dry-run 模式：跳过视频解码，使用空白占位图帧[/yellow]")
    else:
        if not args.video:
            raise SystemExit("非 dry-run 模式下必须提供 --video")
        video_path = Path(args.video)
        if not video_path.exists():
            raise SystemExit(f"视频文件不存在: {video_path}")
        frames = sample_frames(
            str(video_path),
            frames_per_min=strategy.frames_per_min,
            max_frames=min(args.max_frames, strategy.max_frames),
        )

    # 2) 构建 Provider
    provider = build_provider(cfg)

    # 3) 画面解析
    visual_notes = parse_frames_with_vlm(
        provider=provider,
        model=cfg.vlm_model,
        frames=frames,
        strategy=strategy,
        dry_run=args.dry_run,
    )

    # 4) 总结
    result = summarize_video(
        provider=provider,
        model=cfg.llm_model,
        subtitles_text=subs_text,
        visual_notes=visual_notes,
        language=strategy.language,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    rprint(f"[green]已写入[/green] {out_path}")


if __name__ == "__main__":
    main()
