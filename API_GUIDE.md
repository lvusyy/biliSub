# 哔哩哔哩字幕处理系统API使用指南

本文档介绍如何使用哔哩哔哩字幕处理系统API进行视频字幕的提取和处理。

## 系统概述

哔哩哔哩字幕处理系统API是一个RESTful服务，允许用户通过API接口提交B站视频URL，获取字幕内容并支持多种字幕格式转换和语音识别功能。系统采用异步处理机制，支持大型视频文件处理，并提供任务状态查询和结果获取接口。

## 环境要求

- Python 3.8+
- FFmpeg (用于语音识别功能)
- requirements.txt中列出的所有依赖

## 安装与启动

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 配置环境变量（可选）：
   ```bash
   # Linux/macOS
   export BILI_SESSDATA="你的SESSDATA值"
   export BILI_JCT="你的bili_jct值"
   export BILI_BUVID3="你的buvid3值"
   
   # Windows
   set BILI_SESSDATA=你的SESSDATA值
   set BILI_JCT=你的bili_jct值
   set BILI_BUVID3=你的buvid3值
   ```

3. 启动API服务器：
   ```bash
   python bilisub_api.py
   ```
   服务器默认在 http://localhost:8000 上运行

## API密钥

API使用密钥进行身份验证和访问控制。在测试环境中，可以使用以下密钥：
- 测试密钥: `test_key`

在生产环境中，应该配置更安全的密钥管理机制。

## API端点说明

### 1. 创建字幕处理任务

- **URL**: `/api/tasks`
- **方法**: POST
- **描述**: 创建一个新的字幕处理任务
- **请求头**:
  - `X-API-Key`: API密钥
- **请求体**:
  ```json
  {
    "url": "https://www.bilibili.com/video/BV1xx411c79H",
    "credentials": {
      "sessdata": "你的SESSDATA值",
      "bili_jct": "你的bili_jct值",
      "buvid3": "你的buvid3值"
    },
    "output_formats": ["srt", "ass", "vtt"],
    "use_asr": true,
    "asr_model": "small",
    "asr_lang": "zh",
    "callback_url": "https://your-server.com/callback"
  }
  ```
- **响应**:
  ```json
  {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "created_at": "2025-03-01T10:30:00.000000",
    "updated_at": "2025-03-01T10:30:00.000000",
    "progress": 0,
    "video_info": null,
    "error": null
  }
  ```

### 2. 查询任务状态

- **URL**: `/api/tasks/{task_id}`
- **方法**: GET
- **描述**: 获取任务的当前状态
- **请求头**:
  - `X-API-Key`: API密钥
- **响应**:
  ```json
  {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "processing",
    "created_at": "2025-03-01T10:30:00.000000",
    "updated_at": "2025-03-01T10:30:05.000000",
    "progress": 45.5,
    "video_info": {
      "bvid": "BV1xx411c79H",
      "title": "视频标题",
      "duration": 120.5
    },
    "error": null
  }
  ```

### 3. 获取任务结果

- **URL**: `/api/tasks/{task_id}/result`
- **方法**: GET
- **描述**: 获取已完成任务的结果
- **请求头**:
  - `X-API-Key`: API密钥
- **响应**:
  ```json
  {
    "task_id": "550e8400-e29b-41d4-a716-446655440000",
    "files": ["视频标题.srt", "视频标题.ass", "视频标题.vtt"],
    "stats": {
      "success": 1,
      "total_videos": 1,
      "asr_used": 0
    },
    "download_urls": {
      "视频标题.srt": "/api/download/550e8400-e29b-41d4-a716-446655440000/视频标题.srt",
      "视频标题.ass": "/api/download/550e8400-e29b-41d4-a716-446655440000/视频标题.ass",
      "视频标题.vtt": "/api/download/550e8400-e29b-41d4-a716-446655440000/视频标题.vtt"
    }
  }
  ```

### 4. 下载字幕文件

- **URL**: `/api/download/{task_id}/{filename}`
- **方法**: GET
- **描述**: 下载生成的字幕文件
- **请求头**:
  - `X-API-Key`: API密钥
- **响应**: 字幕文件内容（相应的MIME类型）

### 5. 删除任务

- **URL**: `/api/tasks/{task_id}`
- **方法**: DELETE
- **描述**: 删除任务及其相关资源
- **请求头**:
  - `X-API-Key`: API密钥
- **响应**:
  ```json
  {
    "message": "任务已删除: 550e8400-e29b-41d4-a716-446655440000"
  }
  ```

## 使用客户端示例

项目提供了`bilisub_api_client.py`客户端示例，可以方便地调用API：

```bash
# 基本用法
python bilisub_api_client.py -u "https://www.bilibili.com/video/BV1xx411c79H"

# 指定API服务器和密钥
python bilisub_api_client.py -u "https://www.bilibili.com/video/BV1xx411c79H" -s "http://localhost:8000" -k "test_key"

# 指定输出格式
python bilisub_api_client.py -u "https://www.bilibili.com/video/BV1xx411c79H" -f "srt,ass,vtt"

# 禁用语音识别
python bilisub_api_client.py -u "https://www.bilibili.com/video/BV1xx411c79H" --no-asr
```

## 状态码和错误处理

- **200 OK**: 请求成功
- **400 Bad Request**: 请求参数错误
- **401 Unauthorized**: 未提供API密钥或密钥无效
- **403 Forbidden**: 无权访问资源
- **404 Not Found**: 资源不存在
- **429 Too Many Requests**: 请求过于频繁
- **500 Internal Server Error**: 服务器内部错误

错误响应示例：
```json
{
  "detail": "无效的API密钥"
}
```

## 最佳实践

1. **合理设置并发**：API默认限制每分钟10个请求，请合理规划并发量。
2. **定期清理资源**：已完成的任务资源不会自动删除，请定期调用删除接口。
3. **针对大视频的处理**：处理大视频时，可能需要较长时间，请使用状态查询接口监控进度。
4. **凭据安全**：B站账号凭据应通过HTTPS传输，避免使用HTTP。
5. **设置回调URL**：对于耗时较长的任务，建议设置callback_url接收处理完成通知。

## 高级配置

通过修改`bilisub_api.py`中的常量，可以调整API的高级配置：

- `RATE_LIMIT`: 速率限制配置
- `RESULT_DIR`: 结果存储目录
- `API_KEYS`: API密钥配置

## 常见问题

1. **Q**: 如何获取B站账号凭据(SESSDATA, bili_jct, buvid3)?  
   **A**: 登录B站网页版后，通过浏览器开发者工具查看Cookies即可获取。

2. **Q**: 语音识别需要多长时间?  
   **A**: 取决于视频长度和选用的模型。tiny模型速度快但准确率低，large模型准确率高但速度慢。

3. **Q**: 支持哪些字幕格式?  
   **A**: 目前支持srt, ass, vtt, json, txt, lrc六种格式。