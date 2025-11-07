# 哔哩哔哩字幕下载工具 (BiliSub)

一个功能强大的哔哩哔哩视频字幕下载和处理工具，支持官方字幕提取和自动语音识别。

## 主要功能

- 从视频URL或包含URL列表的文件批量下载字幕
- 支持多种字幕格式输出：SRT、ASS、VTT、JSON、TXT、LRC
- 当视频没有官方字幕时，自动使用语音识别生成字幕
- 支持双语字幕处理和对齐
- 字幕清理和优化，包括去除广告、合并相邻时间轴等
- 丰富的配置选项和错误处理机制
- 详细的下载报告和日志

## 安装

### 环境要求

- Python 3.8+

### 安装步骤

1. 克隆或下载本仓库
2. 安装依赖库

```bash
pip install -r requirements.txt
```

3. （可选）配置B站账号Cookie环境变量以访问会员专享内容

```bash
# Windows
set BILI_SESSDATA=你的SESSDATA
set BILI_JCT=你的bili_jct
set BILI_BUVID3=你的buvid3

# Linux/Mac
export BILI_SESSDATA=你的SESSDATA
export BILI_JCT=你的bili_jct
export BILI_BUVID3=你的buvid3
```

## 使用方法

### 基本用法

```bash
# 下载单个视频字幕
python enhanced_bilisub.py -i "https://www.bilibili.com/video/BV1xx411c79H"

# 从文件批量下载
python enhanced_bilisub.py -i urls.txt

# 指定输出格式
python enhanced_bilisub.py -i "https://www.bilibili.com/video/BV1xx411c79H" -f srt,ass,vtt

# 使用代理
python enhanced_bilisub.py -i "https://www.bilibili.com/video/BV1xx411c79H" --proxy "http://127.0.0.1:7890"
```

### 命令行参数

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `-i, --input` | 输入源（URL或文件路径） | 必填 |
| `-o, --output` | 输出目录 | output |
| `-c, --concurrency` | 并发请求数 | 3 |
| `-f, --formats` | 输出格式，以逗号分隔，可选: srt,ass,vtt,json,txt,lrc | srt |
| `--proxy` | 代理设置 | 无 |
| `--use-asr` | 无字幕时使用语音识别 | 开启 |
| `--no-asr` | 禁用语音识别 | - |
| `--asr-model` | 语音识别模型 (tiny, base, small, medium, large) | small |
| `--asr-lang` | 语音识别语言 | zh |
| `--save-audio` | 保存临时音频文件 | 关闭 |

## 字幕格式说明

1. **SRT**: 最常用的字幕格式，被大多数视频播放器支持
2. **ASS**: 高级字幕格式，支持更多样式和效果
3. **VTT**: Web视频字幕格式，HTML5视频支持
4. **JSON**: 包含详细信息的字幕数据，适合进一步处理
5. **TXT**: 纯文本格式，只包含字幕文本
6. **LRC**: 歌词格式，适合音频文件

## 语音识别

本工具使用OpenAI的Whisper模型进行语音识别。模型大小和性能对比：

| 模型 | 参数大小 | 处理速度 | 精度 | 内存占用 |
| --- | --- | --- | --- | --- |
| tiny | 39M | 极快 | 较低 | 非常小 |
| base | 74M | 快 | 一般 | 小 |
| small | 244M | 中等 | 较高 | 中等 |
| medium | 769M | 慢 | 高 | 大 |
| large | 1550M | 极慢 | 非常高 | 非常大 |

首次运行时会自动下载所需模型文件。对于中文识别，建议至少使用small模型以获得较好效果。

## 示例

### 下载单个视频的字幕并输出多种格式

```bash
python enhanced_bilisub.py -i "https://www.bilibili.com/video/BV1xx411c79H" -f srt,ass,vtt,txt
```

### 批量下载多个视频的字幕

创建一个`urls.txt`文件，每行一个视频URL：

```
https://www.bilibili.com/video/BV1xx411c79H
https://www.bilibili.com/video/BV1Gx411w7sV
https://www.bilibili.com/video/BV1Zx411c7nT
```

然后执行：

```bash
python enhanced_bilisub.py -i urls.txt -c 5
```

### 使用高质量语音识别模型

```bash
python enhanced_bilisub.py -i "https://www.bilibili.com/video/BV1xx411c79H" --asr-model medium
```

## 注意事项

1. 使用语音识别功能需要下载对应的模型文件，首次运行可能需要较长时间
2. 大型模型(medium/large)需要较强的硬件配置
3. 对于长视频，处理时间可能较长
4. B站对API有请求频率限制，批量下载时建议适当控制并发数
5. 若遇到"请求被拒绝"错误，可能是IP被临时封锁，建议使用代理或降低请求频率

## V2：画面解析与总结（实验性）

该版本在原有字幕下载/ASR 的基础上，新增“根据字幕自适应地选择视频画面解析策略”，再将“字幕 + 画面要点”融合，由大模型生成结构化总结。

- 自适应策略：根据字幕关键词与语言，推断类型（教程/幻灯片/游戏/访谈/电影等），自动设置帧采样频率与视觉提示风格。
- 多提供方接入：
  - OpenRouter（需 `OPENROUTER_API_KEY`）
  - OpenAI 兼容（OpenAI/自建/vLLM，支持 `--base-url` 与 `OPENAI_API_KEY`）
  - Ollama 本地多模态（`--base-url http://localhost:11434`）
  - Mock（离线联通性测试，不调用网络）
- 输出：包含 `title/topics/timeline/key_takeaways/action_items/final_summary` 的 JSON。

安装依赖：

```bash
pip install -r requirements.txt
```

快速体验（离线）：

```bash
python -m bilisub --subs README.md --provider mock --dry-run --out output/v2_demo.json
```

使用 OpenRouter + Qwen-VL：

```bash
# 先设置密钥（请自行替换）
# Windows PowerShell
$Env:OPENROUTER_API_KEY = "{{OPENROUTER_API_KEY}}"

python -m bilisub \
  --video path/to/video.mp4 \
  --subs  path/to/subs.srt \
  --provider openrouter \
  --vlm-model qwen2.5-vl-7b-instruct \
  --llm-model qwen2.5-7b-instruct \
  --out output/v2_summary.json
```

使用 vLLM（OpenAI 兼容）：

```bash
python -m bilisub \
  --video path/to/video.mp4 \
  --subs  path/to/subs.srt \
  --provider vllm \
  --base-url http://localhost:8000/v1 \
  --api-key-env OPENAI_API_KEY \
  --vlm-model qwen2.5-vl-7b-instruct \
  --llm-model qwen2.5-7b-instruct
```

使用 Ollama：

```bash
python -m bilisub \
  --video path/to/video.mp4 \
  --subs  path/to/subs.srt \
  --provider ollama \
  --base-url http://localhost:11434 \
  --vlm-model llava:13b \
  --llm-model qwen2.5:7b
```

常用参数：
- `--max-frames` 控制最多采样的帧数（默认 40）。
- `--language` 指定总结语言（`auto/zh/en`）。

桥接现有下载流程（V1 -> V2）：

```bash
# 在 V1 生成字幕后，执行：
python bridge_v1_v2.py --output-dir output \
  --video path/to/video.mp4 \
  --provider openrouter \
  --vlm-model qwen3-vl \
  --llm-model qwen2.5-7b-instruct \
  --out output/v2_summary_from_v1.json
```

- `--output-dir` 会在该目录下递归查找最新的 `.srt/.ass/.vtt/.txt/.json` 字幕文件。
- 若未提供 `--video` 则使用 `dry-run` 路径跑通管线（仅验证，结果有限）。

---

## 项目结构

```
biliSub/
├── enhanced_bilisub.py   # 增强版主程序
├── bilibiliSub.py        # 基础版程序
├── requirements.txt      # 依赖库列表
├── README.md             # 说明文档
├── bilisub/              # V2 实现（本次新增）
│   ├── cli.py            # 命令行入口（python -m bilisub）
│   ├── config.py         # 配置与Provider选择
│   ├── strategy.py       # 字幕驱动的策略决策
│   ├── frames.py         # 帧采样工具（OpenCV）
│   ├── vlm.py            # 画面解析编排（VLM 调用）
│   ├── summarize.py      # 融合字幕+画面进行总结
│   └── providers/        # 各平台对接（OpenRouter/OpenAI兼容/Ollama/Mock）
└── output/               # 输出目录
    └── temp/             # 临时文件目录
```

## 更新日志

### v1.0.0 (2025-03-01)
- 首次发布
- 支持官方字幕下载和自动语音识别
- 支持多种字幕格式输出
- 实现批量下载和格式转换

## 许可证

MIT

## 致谢

本项目参考了以下开源项目：
- [Bili23-Downloader](https://github.com/ScottSloan/Bili23-Downloader)
- [bilibili-api](https://github.com/nemo2011/bilibili-api)
- [whisper](https://github.com/openai/whisper)