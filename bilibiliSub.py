import argparse
import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Dict, Tuple, Optional
import requests

from bilibili_api import video, Credential
from tenacity import retry, stop_after_attempt, wait_fixed

# 配置参数
DEFAULT_CONFIG = {
    "concurrency": 3,
    "retry_attempts": 5,
    "request_interval": 1.5,
    "proxy": None
}

@dataclass
class SubtitleSegment:
    start: float
    end: float
    content: str
    lang: str
    position: Tuple[int, int] = (0, 0)

@dataclass
class VideoTask:
    url: str
    bvid: str
    resolution: str
    subs: List[SubtitleSegment]
    duration: float

class BiliSubDownloader:
    def __init__(self, config: dict):
        self.config = {**DEFAULT_CONFIG, **config}
        self.credential = self._init_credential()
        self.stats = {
            "total_videos": 0,
            "success": 0,
            "failed": 0,
            "sub_coverage": 0.0,
            "bilingual_match": 0.0
        }

    def _init_credential(self):
        """从环境变量初始化凭证"""
        return Credential(
            sessdata=os.getenv("BILI_SESSDATA"),
            bili_jct=os.getenv("BILI_JCT"),
            buvid3=os.getenv("BILI_BUVID3")
        )

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def fetch_subs(self, bvid: str) -> Dict:
        """获取视频字幕数据"""
        v = video.Video(bvid=bvid, credential=self.credential)
        info = await v.get_info()
        return {
            "subtitles": await v.get_subtitle_list(),
            "resolution": f"{info['dimension']['width']}x{info['dimension']['height']}",
            "duration": info["duration"]
        }

    def parse_input(self, input_source: str) -> List[VideoTask]:
        """解析输入源（单个URL或文件路径）"""
        if os.path.isfile(input_source):
            with open(input_source, 'r') as f:
                return [self._create_task(url.strip()) for url in f.readlines()]
        return [self._create_task(input_source)]

    def _create_task(self, url: str) -> VideoTask:
        """从URL创建下载任务"""
        bvid = re.search(r"BV\w+", url).group()
        return VideoTask(
            url=url,
            bvid=bvid,
            resolution="1080p",
            subs=[],
            duration=0.0
        )

    async def process_tasks(self, tasks: List[VideoTask]):
        """并发处理多个视频任务"""
        semaphore = asyncio.Semaphore(self.config["concurrency"])
        async with semaphore:
            await asyncio.gather(*[self.process_single_task(task) for task in tasks])

    async def process_single_task(self, task: VideoTask):
        """处理单个视频任务"""
        try:
            subs_data = await self.fetch_subs(task.bvid)
            task.subs = self._process_subs(subs_data["subtitles"])
            task.resolution = subs_data["resolution"]
            task.duration = subs_data["duration"]
            self._generate_output(task)
            
            # 统计有效字幕信息
            for sub in task.subs:
                if '\n' in sub.content:
                    self.stats["bilingual_match"] += 1
                if task.duration > 0:
                    self.stats["sub_coverage"] += (sub.end - sub.start)/task.duration
            self.stats["success"] += 1
        except Exception as e:
            self.stats["failed"] += 1
            print(f"Error processing {task.bvid}: {str(e)}")

    def _process_subs(self, raw_subs: Dict) -> List[SubtitleSegment]:
        """处理原始字幕数据（支持自动生成和人工字幕）"""
        processed = []
        for sub in raw_subs["subtitles"]:
            # 获取字幕类型（自动生成/人工添加）
            sub_type = "auto" if sub["ai_type"] == 1 else "manual"
            
            # 获取字幕内容并预处理
            content = self._fetch_subtitle_content(sub["subtitle_url"])
            cleaned_content = self._clean_subtitle(content)
            
            # 解析时间轴和位置信息
            for segment in self._parse_subtitle_timeline(cleaned_content):
                if not self._is_valid_segment(segment):
                    continue
                
                # 创建字幕片段
                subtitle = SubtitleSegment(
                    start=segment["from"],
                    end=segment["to"],
                    content=self._process_bilingual(segment["content"]),
                    lang=sub["lan"],
                    position=self._calc_position(sub["lan"], segment)
                )
                processed.append(subtitle)
                
                # 统计逻辑（增加异常处理和类型检查）
                try:
                    if not all(key in segment for key in ("from", "to", "content")):
                        raise KeyError("Missing required segment fields")
                        
                    duration = subtitle.end - subtitle.start
                    if duration <= 0:
                        continue
                        
                    # 双语匹配统计
                    if '\n' in subtitle.content:
                        self.stats["bilingual_match"] += 1
                        
                    # 字幕覆盖率统计
                    if self.stats["success"] > 0:  # 防止除以零
                        self.stats["sub_coverage"] += duration / self.stats["success"]
                        
                except (KeyError, TypeError) as e:
                    print(f"统计错误：无效的字幕段数据 {str(e)}")
        return processed

    def _fetch_subtitle_content(self, url: str) -> str:
        """获取字幕文件内容"""
        # 添加B站API必需的请求头
        headers = {
            "Referer": "https://www.bilibili.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8'
        return response.text

    def _process_bilingual(self, content: str) -> str:
        """处理双语字幕（支持多种分隔符）"""
        # 改进的分隔符匹配模式，支持更多种常见分隔方式
        separators = r'(\[EN\]|【EN】|/|\\|\(EN\)|（英）|\||\s-\s)'
        parts = re.split(separators, content, maxsplit=1)
        
        # 提取并清理中英文字幕部分
        zh_part = re.sub(r'\{.*?\}|【.*?】', '', parts[0].strip())
        en_part = re.sub(r'\{.*?\}|【.*?】', '', parts[-1].strip()) if len(parts) > 2 else ""
        
        # 双语对齐处理
        if en_part and len(zh_part.split()) * 1.5 < len(en_part.split()):
            en_part = " ".join(en_part.split())  # 压缩多余空格
            
        return f"{zh_part}\n{en_part}" if en_part else zh_part

    def _clean_subtitle(self, content: str) -> str:
        """字幕预处理：去广告、合并时间轴"""
        # 去除推广文本
        content = re.sub(r"关注.*?获取更多精彩内容", "", content)
        content = re.sub(r"#.*?#", "", content)
        
        # 合并相邻时间轴（间隔小于0.5秒）
        lines = content.split('\n')
        cleaned = []
        prev_end = 0
        for line in lines:
            if match := re.match(r"\[(\d+\.\d+),(\d+\.\d+)\](.*)", line):
                start, end, text = match.groups()
                start = float(start)
                end = float(end)
                if start - prev_end < 0.5 and cleaned:
                    last = cleaned.pop()
                    new_start = last["from"]
                    new_text = f"{last['content']} {text}"
                    cleaned.append({"from": new_start, "to": end, "content": new_text})
                else:
                    cleaned.append({"from": start, "to": end, "content": text})
                prev_end = end
        return json.dumps(cleaned)

    def _parse_subtitle_timeline(self, json_content: str) -> List[dict]:
        """解析JSON格式的字幕时间轴"""
        try:
            return json.loads(json_content)
        except json.JSONDecodeError:
            return []

    def _calc_position(self, lang: str, segment: dict) -> Tuple[int, int]:
        """根据语言和分辨率计算字幕位置"""
        try:
            # 解析分辨率并转换为标准格式
            if 'x' in self.resolution:
                width, height = map(int, self.resolution.split('x'))
            else:  # 处理纯数字分辨率值
                height = int(self.resolution.replace('p', ''))
                width = int(height * 16/9)
            
            res_type = "1080p" if height >= 1080 else "720p" if height >= 720 else "360p"
            
            base_y = 85 if lang == "zh" else 75  # 中文在下，英文在上
            position_map = {
                "360p": (10, int(base_y * 0.6)),
                "720p": (20, int(base_y * 0.8)),
                "1080p": (30, base_y)
            }
            return position_map.get(res_type, (30, base_y))
        except Exception as e:
            print(f"分辨率解析错误 {self.resolution}: {str(e)}")
            return (30, 85)  # 默认位置

    def _generate_output(self, task: VideoTask):
        """生成输出文件"""
        base_name = f"{task.bvid}_{task.resolution}"
        self._generate_srt(task.subs, f"{base_name}.srt")
        self._generate_txt(task.subs, f"{base_name}.txt")

    def _generate_srt(self, subs: List[SubtitleSegment], filename: str):
        """生成SRT格式字幕"""
        with open(filename, 'w', encoding='utf-8') as f:
            for i, sub in enumerate(subs, 1):
                start = timedelta(seconds=sub.start)
                end = timedelta(seconds=sub.end)
                f.write(f"{i}\n{start},{end}\n{sub.content}\n\n")

    def _generate_txt(self, subs: List[SubtitleSegment], filename: str):
        """生成TXT格式字幕"""
        with open(filename, 'w', encoding='utf-8') as f:
            for sub in subs:
                f.write(f"{sub.content}\n")

    def generate_report(self):
        """生成统计报告"""
        report = {
            "total_processed": self.stats["total_videos"],
            "success_rate": self.stats["success"] / self.stats["total_videos"],
            "average_coverage": self.stats["sub_coverage"] / self.stats["success"],
            "bilingual_match_rate": self.stats["bilingual_match"] / self.stats["success"]
        }
        with open("download_report.json", 'w') as f:
            json.dump(report, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B站字幕下载工具")
    parser.add_argument("-i", "--input", required=True, help="输入源（URL或文件路径）")
    parser.add_argument("-o", "--output", default="output", help="输出目录")
    parser.add_argument("-c", "--concurrency", type=int, default=3,
                        help="并发请求数")
    parser.add_argument("--proxy", help="代理设置")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    downloader = BiliSubDownloader({
        "concurrency": args.concurrency,
        "proxy": args.proxy
    })
    
    tasks = downloader.parse_input(args.input)
    downloader.stats["total_videos"] = len(tasks)
    
    asyncio.run(downloader.process_tasks(tasks))
    downloader.generate_report()
