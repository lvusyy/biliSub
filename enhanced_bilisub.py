#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
增强版哔哩哔哩字幕下载工具
支持官方字幕下载和自动语音识别
"""
import argparse
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Dict, Tuple, Optional, Union, Any
from enum import Enum
import logging
import requests
import traceback
import aiohttp
from pathlib import Path
import shutil  # 添加此行以检查系统命令

# 尝试导入bilibili_api库，如果不存在则提示用户安装
try:
    from bilibili_api import video, Credential, sync, exceptions as bili_exceptions
    # 正确导入parse_link函数
    from bilibili_api.utils import parse_link
except ImportError:
    print("请安装必要的依赖库: pip install bilibili-api-python==17.1.2")
    exit(1)

try:
    from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
except ImportError:
    print("请安装必要的依赖库: pip install tenacity")
    exit(1)

# 配置日志
logger = logging.getLogger("BiliSub")

# 默认配置
DEFAULT_CONFIG = {
    "concurrency": 3,             # 并发请求数
    "retry_attempts": 5,          # 重试次数
    "request_interval": 1.5,      # 请求间隔(秒)
    "proxy": None,                # 代理设置
    "output_formats": ["srt"],    # 默认输出格式
    "use_asr": True,              # 是否使用自动语音识别
    "asr_model": "small",         # 语音识别模型 (tiny, base, small, medium, large)
    "asr_lang": "zh",             # 语音识别语言
    "threshold": 0.5,             # 语音识别置信度阈值
    "timeout": 30,                # 网络请求超时时间(秒)
    "temp_dir": "temp",           # 临时文件目录
    "output_dir": "output",       # 输出目录
    "save_audio": False,          # 是否保存临时音频文件
    "filter_danmaku": True,       # 是否过滤弹幕噪声
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
}

# 字幕格式枚举
class SubtitleFormat(str, Enum):
    SRT = "srt"
    ASS = "ass"
    VTT = "vtt"
    JSON = "json"
    TXT = "txt"
    LRC = "lrc"

@dataclass
class SubtitleSegment:
    start: float
    end: float
    content: str
    lang: str 
    position: Tuple[int, int] = (0, 0)
    confidence: float = 1.0  # 语音识别置信度
    is_auto: bool = False    # 是否为自动识别字幕

@dataclass
class VideoInfo:
    bvid: str
    aid: int = 0
    title: str = ""
    duration: float = 0.0
    width: int = 1920
    height: int = 1080
    pubdate: int = 0
    owner: Dict = field(default_factory=dict)

@dataclass
class DownloadTask:
    url: str
    bvid: str
    cid: int = 0
    page: int = 1
    title: str = ""
    subtitle_urls: List[Dict] = field(default_factory=list)
    resolution: str = "1080p"
    subs: List[SubtitleSegment] = field(default_factory=list)
    info: VideoInfo = None
    audio_path: str = ""
    error: str = ""
    asr_used: bool = False

class BiliSubDownloader:
    """增强版B站字幕下载器"""
    
    def __init__(self, config: dict = None):
        """初始化下载器
        
        Args:
            config: 配置参数
        """
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.credential = self._init_credential()
        self.whisper_model = None  # 延迟加载语音识别模型
        
        # 创建临时目录
        os.makedirs(self.config["temp_dir"], exist_ok=True)
        
        # 会话和并发控制
        self.session = None
        self.semaphore = None
        
        # 统计数据
        self.stats = {
            "total_videos": 0,
            "success": 0,
            "failed": 0,
            "sub_coverage": 0.0,
            "bilingual_match": 0.0,
            "asr_used": 0,
            "asr_success": 0
        }
        
        # 进度回调（可选）
        self.callback = self.config.get("callback")
        
        # 检查ffmpeg是否安装
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        """检查ffmpeg是否已安装并可用"""
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            logger.warning("未检测到ffmpeg，语音识别功能可能无法正常工作")
            logger.warning("请安装ffmpeg：https://ffmpeg.org/download.html")
            logger.warning("安装后确保ffmpeg在系统PATH中")
            # 如果用户设置了使用ASR，提出明确警告
            if self.config["use_asr"]:
                logger.error("自动语音识别(ASR)需要ffmpeg，但未找到该程序。请安装ffmpeg后重试")

    def _init_credential(self) -> Credential:
        """从环境变量初始化凭证"""
        return Credential(
            sessdata=os.getenv("BILI_SESSDATA", ""),
            bili_jct=os.getenv("BILI_JCT", ""),
            buvid3=os.getenv("BILI_BUVID3", "")
        )

    def _init_whisper_model(self):
        """初始化Whisper语音识别模型"""
        if self.config["use_asr"] and not self.whisper_model:
            try:
                import whisper
                logger.info(f"正在加载Whisper模型 {self.config['asr_model']}...")
                self.whisper_model = whisper.load_model(self.config["asr_model"])
                logger.info("Whisper模型加载完成")
            except Exception as e:
                logger.error(f"加载Whisper模型失败: {str(e)}")
                logger.error("请确保已安装openai-whisper库: pip install openai-whisper")
                self.config["use_asr"] = False

    def parse_input(self, input_source: str) -> List[DownloadTask]:
        """解析输入源（单个URL或文件路径）
        
        Args:
            input_source: URL或包含URL的文件路径
            
        Returns:
            下载任务列表
        """
        tasks = []
        # 如果输入是文件，则从文件读取URL列表
        if os.path.isfile(input_source):
            with open(input_source, 'r', encoding='utf-8') as f:
                urls = [url.strip() for url in f.readlines() if url.strip()]
                for url in urls:
                    try:
                        task = self._create_task_from_url(url)
                        if task:
                            tasks.append(task)
                    except Exception as e:
                        logger.error(f"解析URL失败 {url}: {str(e)}")
        else:
            # 否则视为单个URL
            try:
                task = self._create_task_from_url(input_source)
                if task:
                    tasks.append(task)
            except Exception as e:
                logger.error(f"解析URL失败 {input_source}: {str(e)}")
                
        self.stats["total_videos"] = len(tasks)
        return tasks

    def _create_task_from_url(self, url: str) -> Optional[DownloadTask]:
        """从URL创建下载任务
        
        Args:
            url: 视频URL
            
        Returns:
            下载任务对象
        """
        # 使用bilibili_api的URL解析功能
        try:
            # 修正: 使用正确的parse_link函数
            parse_result = parse_link(url)
            if not parse_result:
                logger.error(f"无法解析URL: {url}")
                return None
                
            if parse_result.get("type") != "video":
                logger.error(f"URL不是视频链接: {url}")
                return None
                
            bvid = parse_result.get("bvid")
            if not bvid:
                logger.error(f"无法获取BVID: {url}")
                return None
                
            # 创建下载任务
            return DownloadTask(
                url=url,
                bvid=bvid,
                page=parse_result.get("page", 1)
            )
        except Exception as e:
            logger.error(f"创建下载任务失败 {url}: {str(e)}")
            # 尝试正则匹配BVID
            if match := re.search(r"BV\w+", url):
                bvid = match.group()
                return DownloadTask(url=url, bvid=bvid)
            raise

    async def setup(self):
        """初始化异步会话和并发控制"""
        # 配置aiohttp会话
        session_timeout = aiohttp.ClientTimeout(total=self.config['timeout'])
        session_headers = {
            "Referer": "https://www.bilibili.com",
            "User-Agent": self.config["user_agent"]
        }
        
        # 设置代理
        proxy = self.config.get("proxy")
        session_kwargs = {}
        if proxy:
            logger.info(f"使用代理: {proxy}")
            session_kwargs["proxy"] = proxy
            
        # 创建会话
        self.session = aiohttp.ClientSession(
            timeout=session_timeout, 
            headers=session_headers,
            **session_kwargs
        )
        
        # 创建并发控制信号量
        self.semaphore = asyncio.Semaphore(self.config["concurrency"])

    async def fetch_video_info(self, task: DownloadTask) -> VideoInfo:
        """获取视频信息
        
        Args:
            task: 下载任务
            
        Returns:
            视频信息对象
        """
        # 使用bilibili_api获取视频信息
        v = video.Video(bvid=task.bvid, credential=self.credential)
        
        info = await v.get_info()
        pages = info.get("pages", [])
        
        # 确保页码有效
        page_index = min(max(task.page - 1, 0), len(pages) - 1) if pages else 0
        
        # 如果有多个分P，获取指定分P的信息
        if pages and len(pages) > page_index:
            page_info = pages[page_index]
            task.cid = page_info.get("cid", 0)
            page_title = page_info.get("part", "")
            if page_title:
                task.title = f"{info.get('title', task.bvid)}_{page_title}"
            else:
                task.title = info.get('title', task.bvid)
        else:
            task.title = info.get('title', task.bvid)
            if pages and len(pages) > 0:
                task.cid = pages[0].get("cid", 0)
                
        # 获取清晰度信息
        dimension = info.get("dimension", {})
        width = dimension.get("width", 1920)
        height = dimension.get("height", 1080)
        task.resolution = f"{width}x{height}"
        
        # 创建视频信息对象
        return VideoInfo(
            bvid=task.bvid,
            aid=info.get("aid", 0),
            title=task.title,
            duration=info.get("duration", 0.0),
            width=width,
            height=height,
            pubdate=info.get("pubdate", 0),
            owner=info.get("owner", {})
        )

    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_fixed(2),
        retry=retry_if_exception_type((requests.RequestException, aiohttp.ClientError, json.JSONDecodeError))
    )
    async def fetch_subtitle_list(self, task: DownloadTask) -> Dict:
        """获取字幕列表
        
        Args:
            task: 下载任务
            
        Returns:
            字幕信息列表
        """
        if not task.cid:
            # 如果没有cid，先获取视频信息
            v = video.Video(bvid=task.bvid, credential=self.credential)
            pages = await v.get_pages()
            
            # 使用指定分P或默认第一个分P
            page_index = min(max(task.page - 1, 0), len(pages) - 1) if pages else 0
            if pages and len(pages) > page_index:
                task.cid = pages[page_index].get("cid", 0)
            elif pages:
                task.cid = pages[0].get("cid", 0)
                
        if not task.cid:
            raise ValueError(f"无法获取视频CID: {task.bvid}")
        
        # 获取字幕列表
        v = video.Video(bvid=task.bvid, credential=self.credential)
        return await v.get_subtitle(cid=task.cid)

    async def download_subtitle(self, subtitle_url: str) -> str:
        """下载字幕内容
        
        Args:
            subtitle_url: 字幕URL
            
        Returns:
            字幕文本内容
        """
        async with self.semaphore:
            try:
                async with self.session.get(subtitle_url) as response:
                    if response.status != 200:
                        logger.error(f"下载字幕失败: {response.status} - {subtitle_url}")
                        return ""
                    
                    content = await response.text()
                    return content
            except aiohttp.ClientError as e:
                logger.error(f"下载字幕请求错误: {str(e)} - {subtitle_url}")
                raise
            except Exception as e:
                logger.error(f"下载字幕异常: {str(e)} - {subtitle_url}")
                raise

    async def download_audio(self, task: DownloadTask) -> str:
        """下载视频音频用于语音识别
        
        Args:
            task: 下载任务
            
        Returns:
            音频文件路径
        """
        if not task.cid:
            logger.error(f"无法获取CID，无法下载音频: {task.bvid}")
            return ""
            
        try:
            v = video.Video(bvid=task.bvid, credential=self.credential)
            
            # 获取音频URL
            urls = await v.get_download_url(cid=task.cid)
            dash_audio = urls.get("dash", {}).get("audio", [])
            
            if not dash_audio:
                logger.error(f"无法获取音频URL: {task.bvid}")
                return ""
                
            # 选择质量最高的音频
            audio_url = sorted(dash_audio, key=lambda x: x.get("bandwidth", 0), reverse=True)[0].get("baseUrl", "")
            
            if not audio_url:
                logger.error(f"无法获取音频下载链接: {task.bvid}")
                return ""
                
            # 下载音频文件，只使用bvid和cid，避免标题中的非法字符
            audio_path = os.path.join(self.config["temp_dir"], f"{task.bvid}_{task.cid}.m4a")
            
            headers = {
                "Referer": "https://www.bilibili.com",
                "User-Agent": self.config["user_agent"],
                "Range": "bytes=0-" 
            }
            
            async with self.semaphore:
                async with self.session.get(audio_url, headers=headers) as response:
                    if response.status not in (200, 206):
                        logger.error(f"下载音频失败: {response.status} - {audio_url}")
                        return ""
                        
                    with open(audio_path, "wb") as f:
                        # 分块下载
                        chunk_size = 1024 * 1024  # 1MB
                        async for chunk in response.content.iter_chunked(chunk_size):
                            f.write(chunk)
                            
            logger.info(f"音频下载完成: {audio_path}")
            return audio_path
        except Exception as e:
            logger.error(f"下载音频异常: {str(e)}")
            return ""

    def speech_to_text(self, audio_path: str) -> List[SubtitleSegment]:
        """使用Whisper进行语音识别
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            字幕片段列表
        """
        if not os.path.exists(audio_path):
            logger.error(f"音频文件不存在: {audio_path}")
            return []
            
        if not self.whisper_model:
            self._init_whisper_model()
            
        if not self.whisper_model:
            logger.error("Whisper模型初始化失败")
            return []
            
        try:
            logger.info(f"开始语音识别: {audio_path}")
            
            # 检查ffmpeg是否可用
            ffmpeg_path = shutil.which("ffmpeg")
            if not ffmpeg_path:
                logger.error("语音识别需要ffmpeg，但未找到该程序。请安装ffmpeg后重试")
                return []
                
            # 进行语音识别
            result = self.whisper_model.transcribe(
                audio_path, 
                language=self.config["asr_lang"],
                verbose=False
            )
            
            segments = []
            # 创建字幕片段列表
            for seg in result.get("segments", []):
                # 过滤低置信度结果
                if seg.get("no_speech_prob", 0) > self.config["threshold"]:
                    continue
                    
                confidence = 1.0 - seg.get("no_speech_prob", 0)
                if confidence < self.config["threshold"]:
                    continue
                    
                text = seg.get("text", "").strip()
                if not text:
                    continue
                    
                # 创建字幕片段
                subtitle = SubtitleSegment(
                    start=seg.get("start", 0.0),
                    end=seg.get("end", 0.0),
                    content=text,
                    lang=self.config["asr_lang"],
                    confidence=confidence,
                    is_auto=True
                )
                segments.append(subtitle)
                
            logger.info(f"语音识别完成，识别了 {len(segments)} 个片段")
            
            # 如果不保留音频文件，则删除
            if not self.config["save_audio"] and os.path.exists(audio_path):
                os.remove(audio_path)
                
            return segments
        except Exception as e:
            logger.error(f"语音识别失败: {str(e)}")
            traceback.print_exc()
            return []

    def parse_subtitle_content(self, content: str) -> List[SubtitleSegment]:
        """解析字幕内容
        
        Args:
            content: 字幕JSON内容
            
        Returns:
            字幕片段列表
        """
        segments = []
        try:
            data = json.loads(content)
            subtitle_content = data.get("body", [])
            
            for item in subtitle_content:
                from_time = item.get("from", 0.0)
                to_time = item.get("to", 0.0)
                text = item.get("content", "").strip()
                
                if not text:
                    continue
                    
                # 创建字幕片段
                subtitle = SubtitleSegment(
                    start=from_time,
                    end=to_time,
                    content=text,
                    lang=data.get("lang", "zh"),
                    is_auto=False
                )
                segments.append(subtitle)
        except json.JSONDecodeError:
            logger.error(f"解析字幕JSON失败: {content[:100]}...")
        except Exception as e:
            logger.error(f"解析字幕内容异常: {str(e)}")
            
        return segments

    def process_bilingual(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        """处理双语字幕
        
        Args:
            segments: 字幕片段列表
            
        Returns:
            处理后的字幕片段列表
        """
        # 获取中文和英文字幕
        zh_segments = [s for s in segments if s.lang == "zh"]
        en_segments = [s for s in segments if s.lang == "en"]
        
        # 如果没有中英文字幕，直接返回原列表
        if not zh_segments or not en_segments:
            return segments
            
        # 按时间排序
        zh_segments.sort(key=lambda x: (x.start, x.end))
        en_segments.sort(key=lambda x: (x.start, x.end))
        
        # 合并字幕
        merged = []
        for zh in zh_segments:
            # 寻找时间重叠的英文字幕
            matching_en = None
            for en in en_segments:
                # 计算重叠度
                overlap_start = max(zh.start, en.start)
                overlap_end = min(zh.end, en.end)
                overlap = max(0, overlap_end - overlap_start)
                
                # 如果重叠超过75%，则认为是匹配的
                zh_duration = zh.end - zh.start
                if zh_duration > 0 and overlap / zh_duration > 0.75:
                    matching_en = en
                    break
                    
            # 合并中英文字幕
            if matching_en:
                zh.content = f"{zh.content}\n{matching_en.content}"
            merged.append(zh)
            
        return merged

    def clean_subtitle(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        """清理字幕内容
        
        Args:
            segments: 字幕片段列表
            
        Returns:
            清理后的字幕片段列表
        """
        cleaned = []
        for segment in segments:
            # 清理广告和特殊标记
            content = re.sub(r"关注.*?获取更多精彩内容", "", segment.content)
            content = re.sub(r"#.*?#", "", content)
            content = re.sub(r"\s*—{2,}\s*", "", content)  # 删除双破折号分隔符
            
            # 删除多余空格
            content = re.sub(r"\s+", " ", content).strip()
            
            # 如果内容为空，则跳过
            if not content:
                continue
                
            # 更新字幕内容
            segment.content = content
            cleaned.append(segment)
            
        # 合并相邻的短字幕
        if len(cleaned) > 1:
            merged = [cleaned[0]]
            for curr in cleaned[1:]:
                prev = merged[-1]
                
                # 如果时间相近，且内容较短，则合并
                time_diff = curr.start - prev.end
                if (time_diff < 0.5 and 
                    len(prev.content) < 20 and 
                    len(curr.content) < 20):
                    # 合并内容和时间
                    prev.content = f"{prev.content} {curr.content}"
                    prev.end = curr.end
                else:
                    merged.append(curr)
            return merged
            
        return cleaned

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除非法字符
        
        Args:
            filename: 原始文件名
            
        Returns:
            清理后的文件名
        """
        # 替换Windows文件系统不支持的字符
        invalid_chars = r'[\\/*?:"<>|]'
        sanitized = re.sub(invalid_chars, '_', filename)
        
        # 限制长度，避免路径过长问题
        if len(sanitized) > 150:
            sanitized = sanitized[:147] + "..."
            
        return sanitized
    
    async def process_video_task(self, task: DownloadTask) -> bool:
        """处理单个视频任务
        
        Args:
            task: 下载任务
            
        Returns:
            处理是否成功
        """
        try:
            # 获取视频信息
            async with self.semaphore:
                task.info = await self.fetch_video_info(task)
            logger.info(f"获取视频信息成功: {task.title}")
            
            # 获取字幕列表
            async with self.semaphore:
                subtitle_list = await self.fetch_subtitle_list(task)
            
            subtitles = subtitle_list.get("subtitles", [])
            logger.info(f"获取到 {len(subtitles)} 个字幕")
            
            # 如果有字幕，则下载处理
            if subtitles:
                segments = []
                
                # 下载所有字幕
                for sub in subtitles:
                    subtitle_url = sub.get("subtitle_url")
                    if not subtitle_url:
                        continue
                        
                    # 有些URL没有协议前缀
                    if not subtitle_url.startswith("http"):
                        subtitle_url = f"https:{subtitle_url}"
                        
                    # 下载字幕内容
                    content = await self.download_subtitle(subtitle_url)
                    if not content:
                        continue
                        
                    # 解析字幕
                    sub_segments = self.parse_subtitle_content(content)
                    
                    # 设置语言
                    lang = sub.get("lan", "zh")
                    for seg in sub_segments:
                        seg.lang = lang
                        
                    # 将分段加入结果列表
                    segments.extend(sub_segments)
                
                # 处理双语字幕
                if segments:
                    segments = self.process_bilingual(segments)
                    segments = self.clean_subtitle(segments)
                    task.subs = segments
                    
            # 如果没有字幕或字幕为空，且启用了ASR，则使用语音识别
            if (not task.subs and self.config["use_asr"]):
                logger.info(f"未找到官方字幕，尝试使用语音识别: {task.bvid}")
                
                # 下载音频
                audio_path = await self.download_audio(task)
                if audio_path:
                    task.audio_path = audio_path
                    
                    # 语音识别
                    asr_segments = self.speech_to_text(audio_path)
                    if asr_segments:
                        task.subs = asr_segments
                        task.asr_used = True
                        self.stats["asr_used"] += 1
                        self.stats["asr_success"] += 1
                        logger.info(f"语音识别成功，生成了 {len(asr_segments)} 个字幕片段")
                    else:
                        logger.warning(f"语音识别未返回有效结果: {task.bvid}")
                        
            # 如果成功获取字幕，生成输出文件
            if task.subs:
                output_dir = os.path.join(self.config["output_dir"], task.bvid)
                os.makedirs(output_dir, exist_ok=True)
                
                # 清理标题，用于文件名
                sanitized_title = self._sanitize_filename(task.title)
                
                for fmt in self.config["output_formats"]:
                    # 安全检查输出格式
                    if fmt not in [e.value for e in SubtitleFormat]:
                        continue
                        
                    # 生成对应格式的字幕文件
                    output_path = os.path.join(output_dir, f"{sanitized_title}.{fmt}")
                    self._generate_subtitle_file(task.subs, output_path, fmt, task.info)
                    logger.info(f"生成{fmt}字幕文件: {output_path}")
                
                self.stats["success"] += 1
                return True
            else:
                logger.error(f"无法获取字幕: {task.bvid}")
                task.error = "无法获取字幕"
                self.stats["failed"] += 1
                return False
                
        except Exception as e:
            logger.error(f"处理视频任务异常: {str(e)}")
            logger.error(traceback.format_exc())
            task.error = str(e)
            self.stats["failed"] += 1
            return False

    async def process_tasks(self, tasks: List[DownloadTask]):
        """处理多个下载任务
        
        Args:
            tasks: 下载任务列表
        """
        # 设置会话
        await self.setup()
        
        # 初始化语音识别模型
        if self.config["use_asr"]:
            self._init_whisper_model()
            
        try:
            # 创建任务列表
            tasks_with_progress = []
            for i, task in enumerate(tasks):
                async def process_with_progress(t, idx):
                    logger.info(f"开始处理第 {idx+1}/{len(tasks)} 个视频: {t.bvid}")
                    result = await self.process_video_task(t)
                    logger.info(f"完成处理第 {idx+1}/{len(tasks)} 个视频: {t.bvid} - {'成功' if result else '失败'}")
                    # 每个任务处理完后稍作延迟，避免请求过于密集
                    await asyncio.sleep(self.config["request_interval"])
                    # 进度回调（0-100）
                    if self.callback:
                        try:
                            self.callback(((idx + 1) / len(tasks)) * 100.0)
                        except Exception:
                            pass
                    return result
                    
                tasks_with_progress.append(process_with_progress(task, i))
                
            # 并发处理任务
            results = await asyncio.gather(*tasks_with_progress, return_exceptions=True)
            
            # 处理异常
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"任务执行异常: {str(result)}")
                    tasks[i].error = str(result)
                    self.stats["failed"] += 1
                    
        finally:
            # 清理会话
            if self.session:
                await self.session.close()
                
        # 生成报告
        self.generate_report(tasks)

    def _generate_subtitle_file(self, segments: List[SubtitleSegment], output_path: str, 
                              format_type: str, video_info: VideoInfo = None):
        """生成字幕文件
        
        Args:
            segments: 字幕片段列表
            output_path: 输出文件路径
            format_type: 输出格式
            video_info: 视频信息
        """
        # 按开始时间排序
        segments.sort(key=lambda x: x.start)
        
        if format_type == SubtitleFormat.SRT:
            self._generate_srt(segments, output_path)
        elif format_type == SubtitleFormat.ASS:
            self._generate_ass(segments, output_path, video_info)
        elif format_type == SubtitleFormat.VTT:
            self._generate_vtt(segments, output_path)
        elif format_type == SubtitleFormat.JSON:
            self._generate_json(segments, output_path, video_info)
        elif format_type == SubtitleFormat.TXT:
            self._generate_txt(segments, output_path)
        elif format_type == SubtitleFormat.LRC:
            self._generate_lrc(segments, output_path)

    def _generate_srt(self, segments: List[SubtitleSegment], output_path: str):
        """生成SRT格式字幕
        
        Args:
            segments: 字幕片段列表
            output_path: 输出文件路径
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                # 转换时间格式 (秒 -> 00:00:00,000)
                start_time = self._format_srt_time(segment.start)
                end_time = self._format_srt_time(segment.end)
                
                # 写入SRT格式
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{segment.content}\n\n")

    def _format_srt_time(self, seconds: float) -> str:
        """格式化SRT时间
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化后的时间字符串 (00:00:00,000)
        """
        ms = int((seconds % 1) * 1000)
        s = int(seconds % 60)
        m = int((seconds / 60) % 60)
        h = int(seconds / 3600)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def _generate_ass(self, segments: List[SubtitleSegment], output_path: str, video_info: VideoInfo = None):
        """生成ASS格式字幕
        
        Args:
            segments: 字幕片段列表
            output_path: 输出文件路径
            video_info: 视频信息
        """
        # 获取视频分辨率
        width = 1920
        height = 1080
        
        if video_info:
            width = video_info.width or width
            height = video_info.height or height
            
        # ASS文件头
        header = f"""[Script Info]
; Script generated by BiliSub
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
Collisions: Normal
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,思源黑体 CN Medium,50,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,20,0
Style: ZH,思源黑体 CN Medium,50,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,20,0
Style: EN,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,10,10,60,0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(header)
            
            for segment in segments:
                start_time = self._format_ass_time(segment.start)
                end_time = self._format_ass_time(segment.end)
                
                # 处理双语字幕
                if "\n" in segment.content:
                    parts = segment.content.split('\n', 1)
                    zh_text = parts[0].strip()
                    en_text = parts[1].strip() if len(parts) > 1 else ""
                    
                    # 中文字幕
                    if zh_text:
                        f.write(f"Dialogue: 0,{start_time},{end_time},ZH,,0,0,0,,{zh_text}\n")
                    
                    # 英文字幕
                    if en_text:
                        f.write(f"Dialogue: 0,{start_time},{end_time},EN,,0,0,0,,{en_text}\n")
                else:
                    # 单语字幕
                    style = "ZH" if segment.lang == "zh" else "EN"
                    f.write(f"Dialogue: 0,{start_time},{end_time},{style},,0,0,0,,{segment.content}\n")

    def _format_ass_time(self, seconds: float) -> str:
        """格式化ASS时间
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化后的时间字符串 (0:00:00.00)
        """
        cs = int((seconds % 1) * 100)
        s = int(seconds % 60)
        m = int((seconds / 60) % 60)
        h = int(seconds / 3600)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def _generate_vtt(self, segments: List[SubtitleSegment], output_path: str):
        """生成VTT格式字幕
        
        Args:
            segments: 字幕片段列表
            output_path: 输出文件路径
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")
            
            for i, segment in enumerate(segments, 1):
                start_time = self._format_vtt_time(segment.start)
                end_time = self._format_vtt_time(segment.end)
                
                # 双语字幕处理
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{segment.content}\n\n")

    def _format_vtt_time(self, seconds: float) -> str:
        """格式化VTT时间
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化后的时间字符串 (00:00:00.000)
        """
        ms = int((seconds % 1) * 1000)
        s = int(seconds % 60)
        m = int((seconds / 60) % 60)
        h = int(seconds / 3600)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    def _generate_json(self, segments: List[SubtitleSegment], output_path: str, video_info: VideoInfo = None):
        """生成JSON格式字幕
        
        Args:
            segments: 字幕片段列表
            output_path: 输出文件路径
            video_info: 视频信息
        """
        data = {
            "video": {
                "bvid": video_info.bvid if video_info else "",
                "title": video_info.title if video_info else "",
                "duration": video_info.duration if video_info else 0
            },
            "subtitles": []
        }
        
        for segment in segments:
            # 分离双语字幕
            zh_content = segment.content
            en_content = ""
            
            if "\n" in segment.content:
                parts = segment.content.split('\n', 1)
                zh_content = parts[0].strip()
                en_content = parts[1].strip() if len(parts) > 1 else ""
                
            # 添加字幕片段
            data["subtitles"].append({
                "start": segment.start,
                "end": segment.end,
                "content": segment.content,
                "zh": zh_content,
                "en": en_content,
                "lang": segment.lang,
                "is_auto": segment.is_auto,
                "confidence": segment.confidence
            })
            
        # 写入JSON文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _generate_txt(self, segments: List[SubtitleSegment], output_path: str):
        """生成TXT格式字幕
        
        Args:
            segments: 字幕片段列表
            output_path: 输出文件路径
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            for segment in segments:
                f.write(f"{segment.content}\n")

    def _generate_lrc(self, segments: List[SubtitleSegment], output_path: str):
        """生成LRC格式字幕
        
        Args:
            segments: 字幕片段列表
            output_path: 输出文件路径
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("[ti:Bilibili Subtitle]\n")
            f.write(f"[length:{sum(s.end - s.start for s in segments):.2f}]\n")
            
            for segment in segments:
                start_time = self._format_lrc_time(segment.start)
                f.write(f"[{start_time}]{segment.content}\n")

    def _format_lrc_time(self, seconds: float) -> str:
        """格式化LRC时间
        
        Args:
            seconds: 秒数
            
        Returns:
            格式化后的时间字符串 (00:00.00)
        """
        ms = int((seconds % 1) * 100)
        s = int(seconds % 60)
        m = int(seconds / 60)
        return f"{m:02d}:{s:02d}.{ms:02d}"

    def generate_report(self, tasks: List[DownloadTask]):
        """生成统计报告
        
        Args:
            tasks: 所有处理过的任务
        """
        # 统计基本信息
        total = len(tasks)
        success = sum(1 for t in tasks if t.subs)
        asr_used = sum(1 for t in tasks if t.asr_used)
        
        # 更新统计信息
        self.stats["total_videos"] = total
        self.stats["success"] = success
        self.stats["failed"] = total - success
        self.stats["asr_used"] = asr_used
        
        # 计算平均覆盖率
        if success > 0:
            coverage_sum = 0
            bilingual_count = 0
            
            for task in tasks:
                if not task.subs:
                    continue
                    
                # 计算字幕覆盖率
                if task.info and task.info.duration > 0:
                    sub_duration = sum(s.end - s.start for s in task.subs)
                    coverage_sum += sub_duration / task.info.duration
                    
                # 计算双语字幕比例
                for sub in task.subs:
                    if "\n" in sub.content:
                        bilingual_count += 1
                        
            # 更新统计
            self.stats["sub_coverage"] = coverage_sum / success
            if bilingual_count > 0:
                self.stats["bilingual_match"] = bilingual_count / sum(len(t.subs) for t in tasks if t.subs)
        
        # 准备报告数据
        report = {
            "总计视频数": total,
            "成功处理数": success,
            "失败数": total - success,
            "成功率": f"{(success / total * 100):.2f}%" if total > 0 else "0%",
            "使用ASR数": asr_used,
            "ASR成功率": f"{(self.stats['asr_success'] / asr_used * 100):.2f}%" if asr_used > 0 else "N/A",
            "平均字幕覆盖率": f"{(self.stats['sub_coverage'] * 100):.2f}%" if self.stats["sub_coverage"] > 0 else "N/A",
            "双语字幕比例": f"{(self.stats['bilingual_match'] * 100):.2f}%" if self.stats["bilingual_match"] > 0 else "N/A",
            "处理详情": [
                {
                    "bvid": task.bvid,
                    "标题": task.title,
                    "状态": "成功" if task.subs else "失败",
                    "字幕数": len(task.subs) if task.subs else 0,
                    "使用ASR": "是" if task.asr_used else "否",
                    "错误信息": task.error if task.error else ""
                } 
                for task in tasks
            ]
        }
        
        # 写入JSON报告
        with open("download_report.json", 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            
        # 打印摘要
        logger.info(f"处理完成，总计 {total} 个视频，成功 {success} 个，失败 {total - success} 个")
        if asr_used > 0:
            logger.info(f"使用语音识别 {asr_used} 个视频，成功率 {(self.stats['asr_success'] / asr_used * 100):.2f}%")
        logger.info(f"详细报告已保存至 download_report.json")

def load_config(config_file):
    """从配置文件加载设置
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        配置字典
    """
    try:
        if not os.path.exists(config_file):
            logger.error(f"配置文件不存在: {config_file}")
            return {}
            
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # 处理凭证
        if 'credentials' in config:
            creds = config.pop('credentials', {})
            os.environ.setdefault('BILI_SESSDATA', creds.get('sessdata', ''))
            os.environ.setdefault('BILI_JCT', creds.get('bili_jct', ''))
            os.environ.setdefault('BILI_BUVID3', creds.get('buvid3', ''))
            
        logger.info(f"已从配置文件加载设置: {config_file}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {str(e)}")
        return {}

def main():
    """程序入口"""
    parser = argparse.ArgumentParser(description="增强版B站字幕下载工具")
    parser.add_argument("-i", "--input", required=True,
                      help="输入源（URL或文件路径）")
    parser.add_argument("-o", "--output", default="output",
                      help="输出目录")
    parser.add_argument("-c", "--concurrency", type=int, default=3,
                      help="并发请求数")
    parser.add_argument("-f", "--formats", default="srt",
                      help="输出格式，以逗号分隔，可选: srt,ass,vtt,json,txt,lrc")
    parser.add_argument("--proxy", help="代理设置")
    parser.add_argument("--use-asr", action="store_true", default=True,
                      help="无字幕时使用语音识别")
    parser.add_argument("--no-asr", dest="use_asr", action="store_false",
                      help="禁用语音识别")
    parser.add_argument("--asr-model", default="small",
                      help="语音识别模型 (tiny, base, small, medium, large)")
    parser.add_argument("--asr-lang", default="zh",
                      help="语音识别语言")
    parser.add_argument("--save-audio", action="store_true",
                      help="保存临时音频文件")
    parser.add_argument("--config",
                      help="配置文件路径")
    
    args = parser.parse_args()
    
    # 初始化日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("bilisub.log", encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # 创建输出目录（命令行指定的默认目录，会被配置文件覆盖）
    os.makedirs(args.output, exist_ok=True)
    
    # 加载配置文件
    config = {}
    if args.config:
        config = load_config(args.config)
    
    # 解析输出格式
    formats = config.get('output_formats', None)
    if not formats:
        formats = [f.strip() for f in args.formats.split(",")]
        valid_formats = [e.value for e in SubtitleFormat]
        formats = [f for f in formats if f in valid_formats]
    
    if not formats:
        formats = ["srt"]
    
    # 确定输出目录
    output_dir = config.get('output_dir', args.output)
    
    # 创建下载器实例
    downloader_config = {
        "concurrency": config.get('concurrency', args.concurrency),
        "proxy": config.get('proxy', args.proxy),
        "output_formats": formats,
        "use_asr": config.get('use_asr', args.use_asr),
        "asr_model": config.get('asr_model', args.asr_model),
        "asr_lang": config.get('asr_lang', args.asr_lang),
        "save_audio": config.get('save_audio', args.save_audio),
        "temp_dir": os.path.join(output_dir, "temp"),
        "output_dir": output_dir,
    }
    
    # 移除None值
    downloader_config = {k: v for k, v in downloader_config.items() if v is not None}
    
    # 创建下载器实例
    downloader = BiliSubDownloader(downloader_config)
    
    # 解析输入，处理任务
    tasks = downloader.parse_input(args.input)
    
    if not tasks:
        logger.error(f"未找到有效任务: {args.input}")
        return
        
    logger.info(f"开始处理 {len(tasks)} 个视频任务")
    
    # 运行异步任务
    asyncio.run(downloader.process_tasks(tasks))
    
    
if __name__ == "__main__":
    main()