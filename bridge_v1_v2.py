from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional

from rich import print as rprint

from bilisub.api import run_pipeline


SUB_EXTS = (".srt", ".ass", ".vtt", ".txt", ".json")


def find_latest_subs(output_dir: Path) -> Optional[Path]:
    candidates = []
    for ext in SUB_EXTS:
        candidates.extend(output_dir.rglob(f"*{ext}"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="桥接V1输出到V2总结：从既有输出目录中寻找字幕文件并执行V2总结")
    p.add_argument("--output-dir", type=str, default="output", help="V1工具生成字幕的目录（递归查找）")
    p.add_argument("--subs", type=str, default=None, help="显式指定字幕文件（如提供则不再搜索目录）")
    p.add_argument("--video", type=str, default=None, help="视频文件路径（可选；若不提供则使用 dry-run）")
    p.add_argument("--url", type=str, default=None, help="可选：B站视频URL（自动提取BV号）")
    p.add_argument("--bv", type=str, default=None, help="B站视频BV号（用于缓存命中与复用结果）")
    p.add_argument("--cache-readonly", action="store_true", help="只读缓存：命中直接返回，但不写入新结果")
    p.add_argument("--refresh-cache", action="store_true", help="忽略缓存，强制重新解析并覆盖缓存")
    p.add_argument("--save-frames", action="store_true", help="保存采样帧缩略图")
    p.add_argument("--save-frames-dir", type=str, default=None, help="保存帧图片的目录；若未提供且 --save-frames 开启，将按 BV 放入 output/frames/<BV>/")
    p.add_argument("--vlm-req-interval", type=float, default=0.0, help="连续 VLM 请求之间的间隔秒数（限流）")

    p.add_argument("--provider", type=str, default="mock", choices=["openrouter", "openai", "vllm", "ollama", "mock"], help="推理提供方")
    p.add_argument("--vlm-model", type=str, default="qwen2.5-vl-7b-instruct")
    p.add_argument("--llm-model", type=str, default="qwen2.5-7b-instruct")
    p.add_argument("--base-url", type=str, default=None)
    p.add_argument("--api-key-env", type=str, default=None)

    p.add_argument("--language", type=str, default="auto")
    p.add_argument("--max-frames", type=int, default=40)
    p.add_argument("--out", type=str, default="output/v2_summary_from_v1.json")

    args = p.parse_args(argv)

    out_dir = Path(args.output_dir)
    if not out_dir.exists():
        raise SystemExit(f"输出目录不存在: {out_dir}")

    subs = Path(args.subs) if args.subs else find_latest_subs(out_dir)
    if not subs or not subs.exists():
        raise SystemExit(f"未找到可用字幕文件。若未提供 --subs，则会在 {out_dir} 递归查找: {SUB_EXTS}")

    rprint(f"[cyan]使用字幕文件[/cyan]: {subs}")

    api_key = None
    if args.api_key_env:
        api_key = os.environ.get(args.api_key_env)

    # 解析 BV：优先 --bv，其次 --url，其次从文件名推断
    from bilisub.utils import extract_bv_id, derive_bv_from_paths
    derived_bv = args.bv or (extract_bv_id(args.url) if args.url else None) or derive_bv_from_paths(str(subs), args.video)

    # 保存帧目录解析
    save_frames_dir = args.save_frames_dir
    if args.save_frames and not save_frames_dir:
        target_bv = derived_bv or "anon"
        save_frames_dir = str(Path("output/frames") / target_bv)

    result = run_pipeline(
        video_path=args.video,
        subs_path=str(subs),
        provider=args.provider,
        vlm_model=args.vlm_model,
        llm_model=args.llm_model,
        base_url=args.base_url,
        api_key=api_key,
        language=args.language,
        max_frames=args.max_frames,
        dry_run=(args.video is None),
        bv_id=derived_bv,
        source_url=args.url,
        cache_readonly=args.cache_readonly,
        refresh_cache=args.refresh_cache,
        save_frames_dir=save_frames_dir,
        vlm_req_interval=args.vlm_req_interval,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    rprint(f"[green]已写入[/green] {out_path}")


if __name__ == "__main__":
    main()
