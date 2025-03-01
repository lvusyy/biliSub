#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
哔哩哔哩字幕下载器示例脚本
提供简单的交互式界面，方便用户快速尝试
"""
import os
import asyncio
from enhanced_bilisub import BiliSubDownloader, SubtitleFormat

async def main():
    print("=" * 60)
    print("哔哩哔哩字幕下载器示例")
    print("=" * 60)
    
    # 获取用户输入
    url = input("请输入B站视频URL (例如: https://www.bilibili.com/video/BV1xx411c79H): ")
    if not url:
        print("URL不能为空!")
        return
    
    # 选择输出格式
    print("\n请选择字幕输出格式 (多选用逗号分隔):")
    for i, fmt in enumerate([e.value for e in SubtitleFormat], 1):
        print(f"{i}. {fmt}")
    
    formats_input = input("\n请选择格式编号 (默认1): ")
    if not formats_input:
        formats = ["srt"]
    else:
        try:
            indices = [int(idx.strip()) - 1 for idx in formats_input.split(",")]
            formats = [list(SubtitleFormat)[i].value for i in indices if 0 <= i < len(SubtitleFormat)]
            if not formats:
                formats = ["srt"]
        except:
            formats = ["srt"]
    
    # 是否使用语音识别
    use_asr = input("\n当没有官方字幕时，是否使用语音识别生成字幕? (Y/n): ").lower() != "n"
    
    # 选择语音识别模型
    asr_model = "small"
    if use_asr:
        print("\n请选择语音识别模型:")
        models = ["tiny", "base", "small", "medium", "large"]
        for i, model in enumerate(models, 1):
            print(f"{i}. {model} {'(推荐)' if model == 'small' else ''}")
        
        model_input = input("\n请选择模型编号 (默认3): ")
        try:
            model_idx = int(model_input) - 1
            if 0 <= model_idx < len(models):
                asr_model = models[model_idx]
        except:
            pass  # 使用默认值
    
    # 创建输出目录
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    
    # 初始化下载器
    print("\n正在初始化下载器...")
    downloader = BiliSubDownloader({
        "output_formats": formats,
        "use_asr": use_asr,
        "asr_model": asr_model,
        "concurrency": 2,
        "temp_dir": os.path.join(output_dir, "temp")
    })
    
    # 解析输入
    print("正在解析视频URL...")
    tasks = downloader.parse_input(url)
    
    if not tasks:
        print("无法解析视频URL，请检查URL是否正确!")
        return
    
    # 执行下载任务
    print(f"开始处理 {len(tasks)} 个视频...")
    await downloader.process_tasks(tasks)
    
    print("\n处理完成!")
    print(f"字幕文件已保存到 {os.path.abspath(output_dir)} 目录")
    
    # 显示统计信息
    print("\n下载统计:")
    print(f"- 总视频数: {downloader.stats['total_videos']}")
    print(f"- 成功数: {downloader.stats['success']}")
    print(f"- 失败数: {downloader.stats['failed']}")
    
    if downloader.stats["asr_used"] > 0:
        print(f"- 使用语音识别: {downloader.stats['asr_used']} 个视频")
        print(f"- 语音识别成功率: {(downloader.stats['asr_success'] / downloader.stats['asr_used'] * 100):.2f}%")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已中断")
    except Exception as e:
        print(f"\n程序出错: {str(e)}")
    
    input("\n按回车键退出...")