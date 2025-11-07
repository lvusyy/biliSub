# 常见问题与排错（Troubleshooting）

## 1. `ffmpeg` 找不到 / yt-dlp 合并失败
- 需要系统安装 `ffmpeg` 并在 Path 中可用。
- Windows 可使用 `winget install Gyan.FFmpeg` 或手工下载可执行文件放入 Path。

## 2. `ModuleNotFoundError: No module named 'cv2'`
- 非 dry-run 模式需要 `opencv-python`，请执行：`pip install -r requirements.txt`。
- CLI 的 `--dry-run` 模式不需要 opencv。

## 3. `429 Busy: concurrent jobs reached limit`
- 后台 API 的并发上限默认是 3。请等待任务完成后再重试，或提高环境变量 `BILISUB_MAX_CONCURRENCY`。

## 4. Provider 认证失败 / 401
- OpenRouter：确认设置了 `OPENROUTER_API_KEY`。
- OpenAI 兼容/vLLM：确认 `OPENAI_API_KEY` 和 `--base-url` 正确。
- Ollama：确认本地服务运行在 `http://localhost:11434`，且模型支持图像输入。

## 5. 输出为空/结构异常
- 检查所用 VLM 是否支持图像-文本多模态。
- 减小 `--max-frames` 避免超长输入；或使用 `--refresh-cache` 强制重新生成。

## 6. 下载速度慢或受限
- yt-dlp 支持加 Cookie；可查阅其文档使用 `--cookies` 或导入浏览器 Cookies。

## 7. 如何清理/刷新缓存
- 清理：删除 `output/cache/<BV>/` 目录。
- 刷新：运行命令时添加 `--refresh-cache`（CLI/Server 请求体）。

## 8. 如何保存采样帧便于检查
- CLI：添加 `--save-frames`（默认保存到 `output/frames/<BV>/`）。
- 指定目录：`--save-frames-dir output/frames/custom`。

## 9. vLLM/Ollama 兼容性
- 部分模型可能不完全兼容 OpenAI Chat Completions 的图像消息结构；如遇报错，可尝试换模型或改用 OpenRouter。

## 10. 超长视频的性能问题
- 降低 `--max-frames` 或使用更低采样率模型；分段处理后合并要点。
