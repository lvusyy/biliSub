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
    parser.add_argument("--url", type=str, default=None, help="可选：B站视频URL（自动提取BV号）")
    parser.add_argument("--bv", type=str, default=None, help="B站视频BV号（用于缓存命中与复用结果）")
    parser.add_argument("--cache-readonly", action="store_true", help="只读缓存：命中直接返回，但不写入新结果")
    parser.add_argument("--refresh-cache", action="store_true", help="忽略缓存，强制重新解析并覆盖缓存")
    parser.add_argument("--save-frames", action="store_true", help="保存采样帧缩略图")
    parser.add_argument("--save-frames-dir", type=str, default=None, help="保存帧图片的目录；若未提供且 --save-frames 开启，将按 BV 放入 output/frames/<BV>/")
    parser.add_argument("--vlm-req-interval", type=float, default=0.0, help="连续 VLM 请求之间的间隔秒数（限流）")
    parser.add_argument("--one-shot", action="store_true", help="一步到位：通过 --url 下载视频+字幕并直接生成总结")

    args = parser.parse_args(argv)

    cfg = PipelineConfig(
        provider=ProviderKind(args.provider),
        vlm_model=args.vlm_model,
        llm_model=args.llm_model,
        base_url=args.base_url,
        api_key=os.environ.get(args.api_key_env) if args.api_key_env else None,
    )

    # 一步到位路径：若指定 --one-shot 或仅提供 --url 则自动下载视频与字幕
    if args.one_shot or (args.url and not args.video and not args.subs):
        from .one_shot import run_one_shot
        payload = run_one_shot(
            url=args.url or "",
            provider=args.provider,
            vlm_model=args.vlm_model,
            llm_model=args.llm_model,
            base_url=args.base_url,
            api_key=cfg.api_key,
            language=args.language,
            max_frames=args.max_frames,
            refresh_cache=args.refresh_cache,
            cache_readonly=args.cache_readonly,
            vlm_req_interval=args.vlm_req_interval,
            save_frames_dir=None,
        )
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        # 展示策略
        st = payload.get("strategy", {})
        table = Table(title="解析策略")
        table.add_column("维度")
        table.add_column("值")
        table.add_row("内容类型", str(st.get("kind")))
        table.add_row("采样方式", str(st.get("sampling", "uniform")))
        table.add_row("每分钟帧数", str(st.get("frames_per_min")))
        table.add_row("最大帧数", str(st.get("max_frames")))
        table.add_row("VLM提示风格", str(st.get("vlm_prompt_style")))
        console.print(table)
        rprint(f"[green]已写入[/green] {out_path}")
        return

    subs_path = Path(args.subs)
    if not subs_path.exists():
        raise SystemExit(f"字幕文件不存在: {subs_path}")

    # 解析 BV：优先 --bv，其次 --url，其次从文件名推断
    from .utils import extract_bv_id, derive_bv_from_paths
    derived_bv = args.bv or (extract_bv_id(args.url) if args.url else None) or derive_bv_from_paths(str(subs_path), args.video)

    # 保存帧目录解析
    save_frames_dir = args.save_frames_dir
    if args.save_frames and not save_frames_dir:
        target_bv = derived_bv or "anon"
        save_frames_dir = str(Path("output/frames") / target_bv)

    # 直接调用 API（内含缓存逻辑）
    from .api import run_pipeline
    payload = run_pipeline(
        video_path=(None if args.dry_run else (str(Path(args.video)) if args.video else None)),
        subs_path=str(subs_path),
        provider=args.provider,
        vlm_model=args.vlm_model,
        llm_model=args.llm_model,
        base_url=args.base_url,
        api_key=cfg.api_key,
        language=args.language,
        max_frames=args.max_frames,
        dry_run=args.dry_run,
        bv_id=derived_bv,
        source_url=args.url,
        cache_readonly=args.cache_readonly,
        refresh_cache=args.refresh_cache,
        save_frames_dir=save_frames_dir,
        vlm_req_interval=args.vlm_req_interval,
    )

    # 展示解析策略（以结果为准）
    st = payload.get("strategy", {})
    table = Table(title="解析策略")
    table.add_column("维度")
    table.add_column("值")
    table.add_row("内容类型", str(st.get("kind")))
    table.add_row("采样方式", str(st.get("sampling", "uniform")))
    table.add_row("每分钟帧数", str(st.get("frames_per_min")))
    table.add_row("最大帧数", str(st.get("max_frames")))
    table.add_row("VLM提示风格", str(st.get("vlm_prompt_style")))
    console.print(table)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rprint(f"[green]已写入[/green] {out_path}")


if __name__ == "__main__":
    main()
