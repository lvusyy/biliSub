# 快速开始（Quick Start）

本指南带你从零到一跑通“一步到位：URL -> 下载视频/字幕 -> 多模态总结”。

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

前置：需要本机安装 ffmpeg（yt-dlp 合并音视频所需）
- Windows（PowerShell）：
  - winget: `winget install Gyan.FFmpeg`（或在 https://www.gyan.dev/ffmpeg/builds/ 下载解压并将 ffmpeg.exe 所在目录加入 Path）
- Linux: 参考发行版包管理器（例如 `apt install ffmpeg`）
- macOS: `brew install ffmpeg`

验证：`ffmpeg -version`

## 2. 设置推理提供方密钥（示例）

以 OpenRouter 为例（请替换占位值）：
```bash
# PowerShell
$Env:OPENROUTER_API_KEY = "{{OPENROUTER_API_KEY}}"
```

vLLM（OpenAI 兼容）示例：
```bash
# PowerShell
$Env:OPENAI_API_KEY = "{{OPENAI_API_KEY}}"
```

## 3. 一步到位（命令行）

```bash
python -m bilisub \
  --url https://www.bilibili.com/video/BV1xxxxxxx \
  --provider openrouter \
  --vlm-model qwen3-vl \
  --llm-model qwen2.5-7b-instruct \
  --out output/v2_one_shot.json \
  --one-shot
```

输出文件：`output/v2_one_shot.json`

## 4. 后台 API（FastAPI）

启动服务：
```bash
uvicorn bilisub.server:app --host 0.0.0.0 --port 8001
```
- 并发限制：最多 3 个并发任务（可用环境变量 `BILISUB_MAX_CONCURRENCY` 调整）
- 健康检查：GET `http://localhost:8001/health`
- 一步到位：POST `http://localhost:8001/one_shot`
  - 请求体示例：
```json
{
  "url": "https://www.bilibili.com/video/BV1xxxxxxx",
  "provider": "openrouter",
  "vlm_model": "qwen3-vl",
  "llm_model": "qwen2.5-7b-instruct",
  "language": "auto",
  "max_frames": 40,
  "refresh_cache": false,
  "cache_readonly": false,
  "vlm_req_interval": 0.2
}
```

## 5. 其他提供方示例

- vLLM（OpenAI 兼容）：
```bash
python -m bilisub \
  --url https://www.bilibili.com/video/BV1xxxxxxx \
  --provider vllm \
  --base-url http://localhost:8000/v1 \
  --api-key-env OPENAI_API_KEY \
  --vlm-model qwen3-vl \
  --llm-model qwen2.5-7b-instruct \
  --one-shot
```

- Ollama（本地）：
```bash
python -m bilisub \
  --url https://www.bilibili.com/video/BV1xxxxxxx \
  --provider ollama \
  --base-url http://localhost:11434 \
  --vlm-model llava:13b \
  --llm-model qwen2.5:7b \
  --one-shot
```

## 6. 输出与缓存目录

- 结果：`output/*.json`
- 缓存：`output/cache/<BV>/`（latest 与精确配置）
- 暂存作业：`output/jobs/<BV>/video|subs/`
- 可选帧图：`output/frames/<BV>/`（通过 `--save-frames` 开启）
