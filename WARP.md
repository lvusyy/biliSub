# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

BiliSub is a Bilibili (哔哩哔哩) subtitle download and processing tool that supports extracting official subtitles and generating subtitles via automatic speech recognition (ASR) when official subtitles are unavailable. The project includes both a CLI tool and a RESTful API server.

**Language**: Python 3.8+
**Primary Dependencies**: bilibili-api-python, openai-whisper, fastapi, aiohttp, tenacity

## Essential Commands

### Setup and Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Note: ffmpeg is required for ASR functionality
# Check if ffmpeg is installed
ffmpeg -version
```

### Running the CLI Tool
```bash
# Download subtitles from a single video
python enhanced_bilisub.py -i "https://www.bilibili.com/video/BV1xx411c79H"

# Download from a file containing multiple URLs (one per line)
python enhanced_bilisub.py -i urls.txt

# Specify output formats (srt, ass, vtt, json, txt, lrc)
python enhanced_bilisub.py -i "VIDEO_URL" -f srt,ass,vtt

# Control concurrency
python enhanced_bilisub.py -i urls.txt -c 5

# Disable ASR (automatic speech recognition)
python enhanced_bilisub.py -i "VIDEO_URL" --no-asr

# Use specific ASR model (tiny, base, small, medium, large)
python enhanced_bilisub.py -i "VIDEO_URL" --asr-model medium

# Use configuration file
python enhanced_bilisub.py -i "VIDEO_URL" --config config.json

# Use proxy
python enhanced_bilisub.py -i "VIDEO_URL" --proxy "http://127.0.0.1:7890"
```

### Running the API Server
```bash
# Start the FastAPI server
python bilisub_api.py

# Server runs on http://0.0.0.0:8000
# API docs available at http://localhost:8000/docs
```

### Windows Batch Script (Interactive Mode)
```cmd
run_bilisub.bat
```

## Project Architecture

### Core Components

#### 1. Main CLI Tool (`enhanced_bilisub.py`)
The primary entry point for subtitle downloading. Key classes:

- **`BiliSubDownloader`**: Main downloader class that orchestrates the entire workflow
  - Initializes Bilibili API credentials from environment variables
  - Manages async sessions and concurrency control via semaphore
  - Handles both official subtitle extraction and ASR fallback
  - Generates multiple output formats

- **Data Models**:
  - `SubtitleSegment`: Represents a single subtitle with timing, content, language, and confidence
  - `VideoInfo`: Contains video metadata (bvid, aid, title, duration, resolution)
  - `DownloadTask`: Encapsulates a complete download task with status tracking

- **Subtitle Format Support**:
  - SRT (SubRip), ASS (Advanced SubStation), VTT (WebVTT)
  - JSON (with metadata), TXT (plain text), LRC (lyrics format)

#### 2. API Server (`bilisub_api.py`)
RESTful API service built with FastAPI:

- **Authentication**: API key-based authentication via `X-API-Key` header
- **Rate Limiting**: Configurable per-user request limits (default: 10 requests/60 seconds)
- **Async Task Processing**: Background task execution with status tracking
- **Endpoints**:
  - `POST /api/tasks` - Create new subtitle extraction task
  - `GET /api/tasks/{task_id}` - Get task status
  - `GET /api/tasks/{task_id}/result` - Get task results
  - `GET /api/download/{task_id}/{filename}` - Download subtitle file
  - `DELETE /api/tasks/{task_id}` - Delete task
  - `GET /api/stats` - Get API statistics (admin only)

#### 3. Legacy Version (`bilibiliSub.py`)
Basic implementation without ASR support. Kept for backward compatibility.

### Key Workflows

#### Subtitle Download Flow
1. **Parse Input** → Extract BVIDs from URLs using `bilibili_api.utils.parse_link`
2. **Fetch Video Info** → Get video metadata via Bilibili API
3. **Attempt Official Subtitles** → Request subtitle list from API
4. **ASR Fallback** (if enabled and no official subs):
   - Download audio using `bilibili_api` and `aiohttp`
   - Convert to WAV format
   - Process with Whisper model
   - Generate `SubtitleSegment` objects from ASR results
5. **Format Conversion** → Generate requested subtitle formats
6. **Generate Report** → Create JSON report with statistics

#### Authentication & Credentials
The tool uses Bilibili cookies for authenticated access (required for member-only content):
- `BILI_SESSDATA` - Session data
- `BILI_JCT` - CSRF token
- `BILI_BUVID3` - Browser unique ID

These can be set via:
- Environment variables (recommended)
- `config.json` file
- Direct code modification (not recommended)

### Important Implementation Details

#### Concurrency and Rate Limiting
- Uses `asyncio.Semaphore` for controlling concurrent requests
- Default concurrency: 3 simultaneous requests
- Request interval: 1.5 seconds between requests
- Retry mechanism via `tenacity` library (5 attempts by default)

#### ASR (Automatic Speech Recognition)
- Uses OpenAI Whisper models loaded locally
- Models are downloaded on first use
- Model files are cached by the Whisper library
- Requires ffmpeg for audio processing
- Default model: "small" (244MB, balanced speed/accuracy)
- Generates subtitles with confidence scores marked as `is_auto=True`

#### Subtitle Processing Features
- **Bilingual Support**: Handles Chinese/English dual subtitles with proper alignment
- **Cleaning**: Removes advertisements and promotional text using regex patterns
- **Timeline Merging**: Combines adjacent subtitles with gaps < 0.5 seconds
- **Position Calculation**: Computes subtitle positions for different languages

## Configuration

### Configuration File Format (`config.json`)
```json
{
  "credentials": {
    "sessdata": "your_sessdata",
    "bili_jct": "your_bili_jct",
    "buvid3": "your_buvid3"
  },
  "proxy": "http://127.0.0.1:7890",
  "concurrency": 3,
  "output_formats": ["srt", "ass", "vtt"],
  "use_asr": true,
  "asr_model": "small",
  "asr_lang": "zh",
  "save_audio": false
}
```

### Environment Variables
```bash
# Windows (PowerShell)
$env:BILI_SESSDATA = "your_value"
$env:BILI_JCT = "your_value"
$env:BILI_BUVID3 = "your_value"

# Linux/Mac
export BILI_SESSDATA="your_value"
export BILI_JCT="your_value"
export BILI_BUVID3="your_value"
```

## File Structure

```
biliSub/
├── enhanced_bilisub.py      # Main CLI tool (recommended)
├── bilisub_api.py            # RESTful API server
├── bilisub_api_client.py     # API client examples
├── bilibiliSub.py            # Legacy CLI tool (no ASR)
├── example.py                # Usage examples
├── requirements.txt          # Python dependencies
├── config.example.json       # Configuration template
├── config.json               # User config (gitignored)
├── run_bilisub.bat           # Windows interactive launcher
├── README.md                 # Documentation (Chinese)
├── config_guide.md           # Configuration guide (Chinese)
├── API_GUIDE.md              # API documentation
├── output/                   # Generated subtitles (gitignored)
│   └── {bvid}/              # Per-video directories
│       └── temp/            # Temporary audio files
└── api_results/             # API task results (gitignored)
    └── {task_id}/           # Per-task directories
```

## Development Notes

### Testing Considerations
- No test framework is currently implemented in the repository
- Manual testing required through CLI or API endpoints
- Test with various video types: public videos, member-only content, videos with/without official subtitles

### Error Handling
- All network requests include retry logic via `tenacity`
- Comprehensive logging to both console and `bilisub.log` file
- Task-level error tracking in `DownloadTask.error` field
- API returns detailed error messages with appropriate HTTP status codes

### External Dependencies
- **bilibili-api-python**: Primary interface to Bilibili API
- **whisper**: OpenAI's speech recognition model
- **ffmpeg**: Required system dependency for audio processing (not in requirements.txt)
- **aiohttp**: Async HTTP client for concurrent requests
- **fastapi/uvicorn**: API server framework

### Code Style
- Uses Python dataclasses for data models
- Async/await pattern for I/O operations
- Type hints on function signatures
- Docstrings follow basic format (no specific style guide)

### Logging
- Module uses Python's built-in logging
- Log files: `bilisub.log` (CLI) and `bilisub_api.log` (API)
- Log level: INFO by default
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

## Common Issues

1. **"请求被拒绝" (Request Rejected)**: Rate limiting by Bilibili - use proxy or reduce concurrency
2. **Missing ffmpeg**: ASR won't work - install ffmpeg and add to PATH
3. **Whisper model download fails**: Use proxy with `--proxy` flag
4. **Out of memory**: Use smaller ASR model (`--asr-model tiny` or `base`)
5. **Empty subtitles**: Video may have no official subtitles and ASR is disabled
