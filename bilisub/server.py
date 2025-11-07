from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import anyio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .one_shot import run_one_shot

MAX_CONCURRENCY = int(os.environ.get("BILISUB_MAX_CONCURRENCY", "3"))
_sem = asyncio.Semaphore(MAX_CONCURRENCY)

app = FastAPI(title="BiliSub V2 One-Shot API", version="2.0.0")


class OneShotRequest(BaseModel):
    url: str = Field(..., description="B站视频URL")
    provider: str = Field("openrouter")
    vlm_model: str = Field("qwen3-vl")
    llm_model: str = Field("qwen2.5-7b-instruct")
    base_url: Optional[str] = None
    api_key_env: Optional[str] = Field(None, description="从该环境变量读取API Key")
    language: str = Field("auto")
    max_frames: int = Field(40, ge=1, le=200)
    refresh_cache: bool = False
    cache_readonly: bool = False
    vlm_req_interval: float = 0.0


@app.get("/health")
async def health():
    available = _sem._value if hasattr(_sem, "_value") else None
    return {"ok": True, "max_concurrency": MAX_CONCURRENCY, "available_slots": available}


@app.post("/one_shot")
async def one_shot(req: OneShotRequest):
    try:
        _sem.acquire_nowait()
    except Exception:
        raise HTTPException(status_code=429, detail="Busy: concurrent jobs reached limit")

    try:
        api_key = os.environ.get(req.api_key_env) if req.api_key_env else None
        result = await anyio.to_thread.run_sync(
            run_one_shot,
            url=req.url,
            provider=req.provider,
            vlm_model=req.vlm_model,
            llm_model=req.llm_model,
            base_url=req.base_url,
            api_key=api_key,
            language=req.language,
            max_frames=req.max_frames,
            refresh_cache=req.refresh_cache,
            cache_readonly=req.cache_readonly,
            vlm_req_interval=req.vlm_req_interval,
            save_frames_dir=None,
        )
        return result
    finally:
        _sem.release()
