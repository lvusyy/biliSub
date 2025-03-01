# 哔哩哔哩字幕下载工具配置指南

本文档详细说明如何获取和配置本工具所需的各种秘钥和凭证。

## B站账号凭证

B站账号凭证用于访问需要登录才能查看的视频内容（如会员专享视频）。**注意：对于公开视频，这些凭证是可选的**。

### 获取B站账号凭证步骤

1. 使用Chrome或Edge浏览器登录B站账号
2. 按F12打开开发者工具
3. 选择"应用程序"(Application)选项卡
4. 在左侧导航栏中，展开"Cookie"，然后选择"https://www.bilibili.com"
5. 在右侧Cookie列表中，找到并复制以下三个值：
   - `SESSDATA`
   - `bili_jct`
   - `buvid3`

![B站Cookie获取示意图](https://i.imgur.com/example.png)

### 设置B站账号凭证

#### 方法一：环境变量（推荐）

设置环境变量是最安全的方式，避免将敏感信息直接写入代码。

**Windows:**
```cmd
set BILI_SESSDATA=你的SESSDATA值
set BILI_JCT=你的bili_jct值
set BILI_BUVID3=你的buvid3值
```

**Linux/Mac:**
```bash
export BILI_SESSDATA=你的SESSDATA值
export BILI_JCT=你的bili_jct值
export BILI_BUVID3=你的buvid3值
```

#### 方法二：配置文件

创建`config.json`文件（需自行创建），内容如下：

```json
{
  "credentials": {
    "sessdata": "你的SESSDATA值",
    "bili_jct": "你的bili_jct值",
    "buvid3": "你的buvid3值"
  }
}
```

然后在运行时指定配置文件：

```bash
python enhanced_bilisub.py -i "视频URL" --config config.json
```

#### 方法三：直接修改代码

编辑`enhanced_bilisub.py`文件，找到`_init_credential`方法，直接填入你的凭证：

```python
def _init_credential(self) -> Credential:
    """从环境变量初始化凭证"""
    return Credential(
        sessdata="你的SESSDATA值",
        bili_jct="你的bili_jct值",
        buvid3="你的buvid3值"
    )
```

这种方法最不推荐，因为可能会不小心将凭证公开。

## 语音识别模型

本工具使用OpenAI的Whisper本地模型进行语音识别，**无需API密钥**。模型文件会在首次运行时自动下载。

### 模型选择

根据你的需求和硬件配置选择合适的模型：

- `tiny`: 39MB，速度极快，精度较低
- `base`: 74MB，速度快，精度一般
- `small`: 244MB，速度中等，精度较高（默认推荐）
- `medium`: 769MB，速度慢，精度高
- `large`: 1.5GB，速度极慢，精度极高

通过命令行参数选择模型：

```bash
python enhanced_bilisub.py -i "视频URL" --asr-model small
```

### 代理设置

如果在中国大陆地区下载模型文件较慢，可以设置代理：

```bash
python enhanced_bilisub.py -i "视频URL" --proxy "http://127.0.0.1:7890"
```

## 配置文件支持

我已更新工具以支持从配置文件读取设置。创建`config.json`文件：

```json
{
  "credentials": {
    "sessdata": "你的SESSDATA值",
    "bili_jct": "你的bili_jct值",
    "buvid3": "你的buvid3值"
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

然后运行：

```bash
python enhanced_bilisub.py -i "视频URL" --config config.json
```

## 常见问题

1. **凭证无效或过期**
   - B站Cookie通常有效期为一个月，过期后需要重新获取

2. **无法下载会员视频**
   - 确保使用的账号有权限访问该视频
   - 检查Cookie是否正确设置并未过期

3. **语音识别模型下载失败**
   - 检查网络连接
   - 尝试设置代理
   - 手动下载模型文件并放置到正确位置

4. **内存不足错误**
   - 选择更小的语音识别模型（如tiny或base）
   - 增加系统虚拟内存