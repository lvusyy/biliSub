#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
哔哩哔哩字幕处理系统 RESTful API
提供字幕提取和处理服务接口
"""
import os
import json
import time
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse

from enhanced_bilisub import BiliSubDownloader, SubtitleFormat, DownloadTask

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bilisub_api.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("BiliSubAPI")

# 创建FastAPI应用
app = FastAPI(
    title="哔哩哔哩字幕处理API",
    description="提供B站视频字幕提取和处理服务，支持多种字幕格式和语音识别功能",
    version="1.0.0",
)

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境下应该设置为特定的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建存储目录
RESULT_DIR = Path("api_results")
RESULT_DIR.mkdir(exist_ok=True)

# 内存中的任务存储
# 在实际生产环境中应使用数据库
tasks_db = {}  # task_id -> task_info
active_tasks = {}  # 正在处理的任务 task_id -> download_task

# 速率限制配置
RATE_LIMIT = {
    "window_seconds": 60,  # 时间窗口
    "max_requests": 10,    # 最大请求数
}

user_requests = {}  # user_id -> list of request timestamps

# API密钥鉴权（简单实现，生产环境应使用更安全的方式）
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

API_KEYS = {
    # 在生产环境中，应该使用安全存储方式
    "test_key": {"user_id": "test_user", "rate_limit": 10},
}

# 数据模型
class BilibiliCredentials(BaseModel):
    sessdata: str = Field(..., description="B站SESSDATA凭证")
    bili_jct: str = Field(..., description="B站bili_jct凭证")
    buvid3: str = Field(..., description="B站buvid3凭证")

class TaskRequest(BaseModel):
    url: str = Field(..., description="B站视频URL")
    credentials: Optional[BilibiliCredentials] = Field(None, description="B站账号凭证(可选)")
    output_formats: List[str] = Field(["srt"], description="输出格式列表，支持srt,ass,vtt,json,txt,lrc")
    use_asr: bool = Field(True, description="无字幕时是否使用语音识别")
    asr_model: str = Field("small", description="语音识别模型大小(tiny,base,small,medium,large)")
    asr_lang: str = Field("zh", description="语音识别语言")
    callback_url: Optional[HttpUrl] = Field(None, description="任务完成后的回调URL")

class TaskStatus(BaseModel):
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态(pending/processing/completed/failed)")
    created_at: str = Field(..., description="任务创建时间")
    updated_at: str = Field(..., description="任务更新时间")
    progress: Optional[float] = Field(None, description="任务进度(0-100)")
    video_info: Optional[Dict] = Field(None, description="视频信息")
    error: Optional[str] = Field(None, description="错误信息")
    
class TaskResult(BaseModel):
    task_id: str = Field(..., description="任务ID")
    files: List[str] = Field(..., description="生成的文件列表")
    stats: Dict = Field(..., description="任务统计信息")
    download_urls: Dict[str, str] = Field(..., description="下载链接")

# 速率限制中间件
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # 检查API密钥
    api_key = request.headers.get(API_KEY_NAME)
    if not api_key or api_key not in API_KEYS:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "无效的API密钥"}
        )
    
    user_id = API_KEYS[api_key]["user_id"]
    rate_limit = API_KEYS[api_key]["rate_limit"]
    
    # 检查速率限制
    now = time.time()
    if user_id in user_requests:
        # 过滤出时间窗口内的请求
        requests_in_window = [t for t in user_requests[user_id] 
                              if now - t < RATE_LIMIT["window_seconds"]]
        
        if len(requests_in_window) >= rate_limit:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "请求过于频繁，请稍后再试"}
            )
        
        user_requests[user_id] = requests_in_window
    else:
        user_requests[user_id] = []
    
    # 记录本次请求时间
    user_requests[user_id].append(now)
    
    # 继续处理请求
    response = await call_next(request)
    return response

# 验证API密钥
async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key is None or api_key not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的API密钥"
        )
    return api_key

# 下载进度回调
class ProgressCallback:
    def __init__(self, task_id):
        self.task_id = task_id
        self.start_time = time.time()
    
    def update(self, progress):
        tasks_db[self.task_id]["progress"] = progress
        tasks_db[self.task_id]["updated_at"] = datetime.now().isoformat()

# 任务处理函数
async def process_subtitle_task(task_id: str, task_request: TaskRequest):
    try:
        # 更新任务状态
        tasks_db[task_id]["status"] = "processing"
        tasks_db[task_id]["updated_at"] = datetime.now().isoformat()
        
        # 准备配置
        config = {
            "output_formats": task_request.output_formats,
            "use_asr": task_request.use_asr,
            "asr_model": task_request.asr_model,
            "asr_lang": task_request.asr_lang,
            "concurrency": 2,
            "temp_dir": str(RESULT_DIR / task_id / "temp"),
            "callback": ProgressCallback(task_id).update,
        }
        
        # 设置环境变量（如果提供了凭证）
        if task_request.credentials:
            os.environ["BILI_SESSDATA"] = task_request.credentials.sessdata
            os.environ["BILI_JCT"] = task_request.credentials.bili_jct
            os.environ["BILI_BUVID3"] = task_request.credentials.buvid3
        
        # 创建下载器
        downloader = BiliSubDownloader(config)
        
        # 解析视频URL
        task_dir = RESULT_DIR / task_id
        task_dir.mkdir(exist_ok=True)
        
        download_tasks = downloader.parse_input(task_request.url)
        if not download_tasks:
            raise Exception(f"无法解析视频URL: {task_request.url}")
        
        active_tasks[task_id] = download_tasks[0]
        
        # 处理任务
        await downloader.process_tasks(download_tasks)
        
        # 如果处理成功，更新任务状态
        if download_tasks[0].subs:
            # 准备结果数据
            result_files = []
            download_urls = {}
            
            # 收集生成的文件
            output_dir = Path("output") / download_tasks[0].bvid
            if output_dir.exists():
                for fmt in task_request.output_formats:
                    # 查找指定格式的文件
                    for file_path in output_dir.glob(f"*.{fmt}"):
                        # 创建任务特定目录中的副本
                        dest_path = task_dir / file_path.name
                        if not dest_path.exists():
                            shutil.copy(file_path, dest_path)
                        
                        result_files.append(file_path.name)
                        download_urls[file_path.name] = f"/api/download/{task_id}/{file_path.name}"
            
            # 更新任务状态为完成
            tasks_db[task_id].update({
                "status": "completed",
                "updated_at": datetime.now().isoformat(),
                "progress": 100,
                "result": {
                    "files": result_files,
                    "stats": downloader.stats,
                    "download_urls": download_urls,
                }
            })
            
            # 如果提供了回调URL，发送通知
            if task_request.callback_url:
                await send_callback_notification(
                    task_request.callback_url,
                    {
                        "task_id": task_id,
                        "status": "completed",
                        "result_url": f"/api/tasks/{task_id}/result"
                    }
                )
            
            logger.info(f"任务处理完成: {task_id}")
        else:
            # 更新任务状态为失败
            error_msg = "未能获取到字幕"
            if download_tasks[0].error:
                error_msg = download_tasks[0].error
                
            tasks_db[task_id].update({
                "status": "failed",
                "updated_at": datetime.now().isoformat(),
                "error": error_msg,
            })
            
            # 如果提供了回调URL，发送失败通知
            if task_request.callback_url:
                await send_callback_notification(
                    task_request.callback_url,
                    {
                        "task_id": task_id,
                        "status": "failed",
                        "error": error_msg
                    }
                )
            
            logger.error(f"任务处理失败: {task_id} - {error_msg}")
    
    except Exception as e:
        logger.error(f"任务处理异常: {task_id} - {str(e)}")
        # 更新任务状态为失败
        tasks_db[task_id].update({
            "status": "failed",
            "updated_at": datetime.now().isoformat(),
            "error": str(e),
        })
        
        # 如果提供了回调URL，发送失败通知
        if task_request.callback_url:
            await send_callback_notification(
                task_request.callback_url,
                {
                    "task_id": task_id,
                    "status": "failed",
                    "error": str(e)
                }
            )
    
    finally:
        # 清理环境变量
        if task_request.credentials:
            if "BILI_SESSDATA" in os.environ:
                del os.environ["BILI_SESSDATA"]
            if "BILI_JCT" in os.environ:
                del os.environ["BILI_JCT"]
            if "BILI_BUVID3" in os.environ:
                del os.environ["BILI_BUVID3"]
        
        # 从活动任务中移除
        if task_id in active_tasks:
            del active_tasks[task_id]

# 发送回调通知
async def send_callback_notification(callback_url: HttpUrl, data: Dict):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                str(callback_url),
                json=data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    logger.error(f"回调通知失败: {callback_url} - HTTP {response.status}")
                else:
                    logger.info(f"回调通知发送成功: {callback_url}")
    except Exception as e:
        logger.error(f"发送回调通知异常: {callback_url} - {str(e)}")

# API端点
@app.post("/api/tasks", response_model=TaskStatus, summary="创建字幕处理任务")
async def create_task(
    task_request: TaskRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    # 生成任务ID
    task_id = str(uuid.uuid4())
    
    # 创建任务记录
    task_info = {
        "task_id": task_id,
        "request": task_request.dict(),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "progress": 0,
        "user_id": API_KEYS[api_key]["user_id"],
    }
    tasks_db[task_id] = task_info
    
    # 启动后台任务
    background_tasks.add_task(process_subtitle_task, task_id, task_request)
    
    logger.info(f"创建新任务: {task_id} - URL: {task_request.url}")
    
    # 返回任务状态
    return TaskStatus(
        task_id=task_id,
        status="pending",
        created_at=task_info["created_at"],
        updated_at=task_info["updated_at"],
        progress=0,
        error=None,
        video_info=None,
    )

@app.get("/api/tasks/{task_id}", response_model=TaskStatus, summary="查询任务状态")
async def get_task_status(task_id: str, api_key: str = Depends(verify_api_key)):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    
    # 检查权限
    if tasks_db[task_id]["user_id"] != API_KEYS[api_key]["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    task_info = tasks_db[task_id]
    
    # 准备视频信息
    video_info = None
    if task_id in active_tasks and active_tasks[task_id].info:
        video_info = {
            "bvid": active_tasks[task_id].bvid,
            "title": active_tasks[task_id].title,
            "duration": active_tasks[task_id].info.duration if active_tasks[task_id].info else 0,
        }
    
    # 返回任务状态
    return TaskStatus(
        task_id=task_id,
        status=task_info["status"],
        created_at=task_info["created_at"],
        updated_at=task_info["updated_at"],
        progress=task_info.get("progress", 0),
        video_info=video_info,
        error=task_info.get("error")
    )

@app.get("/api/tasks/{task_id}/result", response_model=TaskResult, summary="获取任务结果")
async def get_task_result(task_id: str, api_key: str = Depends(verify_api_key)):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    
    # 检查权限
    if tasks_db[task_id]["user_id"] != API_KEYS[api_key]["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    task_info = tasks_db[task_id]
    
    if task_info["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"任务尚未完成: {task_id}")
    
    if "result" not in task_info:
        raise HTTPException(status_code=500, detail=f"任务结果不可用: {task_id}")
    
    # 返回任务结果
    return TaskResult(
        task_id=task_id,
        files=task_info["result"]["files"],
        stats=task_info["result"]["stats"],
        download_urls=task_info["result"]["download_urls"]
    )

@app.delete("/api/tasks/{task_id}", summary="删除任务")
async def delete_task(task_id: str, api_key: str = Depends(verify_api_key)):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    
    # 检查权限
    if tasks_db[task_id]["user_id"] != API_KEYS[api_key]["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 检查任务是否正在处理
    if task_id in active_tasks:
        raise HTTPException(status_code=400, detail=f"任务正在处理中，无法删除: {task_id}")
    
    # 删除任务记录
    del tasks_db[task_id]
    
    # 删除任务文件
    task_dir = RESULT_DIR / task_id
    if task_dir.exists():
        import shutil
        shutil.rmtree(task_dir)
    
    logger.info(f"删除任务: {task_id}")
    
    return {"message": f"任务已删除: {task_id}"}

@app.get("/api/download/{task_id}/{filename}", summary="下载字幕文件")
async def download_file(task_id: str, filename: str, api_key: str = Depends(verify_api_key)):
    if task_id not in tasks_db:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    
    # 检查权限
    if tasks_db[task_id]["user_id"] != API_KEYS[api_key]["user_id"]:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 检查文件是否存在
    file_path = RESULT_DIR / task_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")
    
    # 设置文件类型
    media_type = "text/plain"
    if filename.endswith(".srt"):
        media_type = "application/x-subrip"
    elif filename.endswith(".ass"):
        media_type = "text/plain"
    elif filename.endswith(".vtt"):
        media_type = "text/vtt"
    elif filename.endswith(".json"):
        media_type = "application/json"
    
    logger.info(f"下载文件: {task_id}/{filename}")
    
    # 返回文件
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type
    )

@app.get("/api/stats", summary="获取API统计信息")
async def get_api_stats(api_key: str = Depends(verify_api_key)):
    # 检查是否为管理员API密钥
    if API_KEYS[api_key]["user_id"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    
    user_id = API_KEYS[api_key]["user_id"]
    
    # 统计任务数量
    total_tasks = len(tasks_db)
    pending_tasks = sum(1 for task in tasks_db.values() if task["status"] == "pending")
    processing_tasks = sum(1 for task in tasks_db.values() if task["status"] == "processing")
    completed_tasks = sum(1 for task in tasks_db.values() if task["status"] == "completed")
    failed_tasks = sum(1 for task in tasks_db.values() if task["status"] == "failed")
    
    # 按用户分组的任务统计
    user_stats = {}
    for task in tasks_db.values():
        user_id = task["user_id"]
        if user_id not in user_stats:
            user_stats[user_id] = {
                "total": 0,
                "completed": 0,
                "failed": 0
            }
        
        user_stats[user_id]["total"] += 1
        if task["status"] == "completed":
            user_stats[user_id]["completed"] += 1
        elif task["status"] == "failed":
            user_stats[user_id]["failed"] += 1
    
    # 返回统计信息
    return {
        "task_stats": {
            "total": total_tasks,
            "pending": pending_tasks,
            "processing": processing_tasks,
            "completed": completed_tasks,
            "failed": failed_tasks,
        },
        "user_stats": user_stats,
        "active_tasks": len(active_tasks),
    }

@app.get("/", summary="API入口页")
async def root():
    return {
        "name": "哔哩哔哩字幕处理API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }

# 启动服务器
if __name__ == "__main__":
    import shutil
    
    # 检查依赖项
    try:
        import aiohttp
        import whisper
    except ImportError:
        print("缺少必要的依赖，请安装：pip install aiohttp openai-whisper fastapi uvicorn")
        exit(1)
    
    # 检查ffmpeg(只在启用ASR时需要)
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        print("警告: 未检测到ffmpeg，语音识别功能可能无法正常工作")
        print("请安装ffmpeg：https://ffmpeg.org/download.html")
    
    # 启动服务器
    uvicorn.run(app, host="0.0.0.0", port=8000)