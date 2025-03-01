@echo off
echo 哔哩哔哩字幕下载工具 (BiliSub)
echo ============================

REM 检查是否已安装依赖
pip show bilibili-api-python >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在安装必要的依赖库...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo 安装依赖失败，请手动执行命令: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

:menu
cls
echo 哔哩哔哩字幕下载工具 (BiliSub)
echo ============================
echo.
echo 请选择操作:
echo 1. 运行交互式示例
echo 2. 下载单个视频字幕 (默认SRT格式)
echo 3. 批量下载视频字幕
echo 4. 生成多种格式字幕 (SRT,ASS,VTT,JSON)
echo 5. 退出
echo.
set /p choice=请输入选项数字: 

if "%choice%"=="1" goto example
if "%choice%"=="2" goto single
if "%choice%"=="3" goto batch
if "%choice%"=="4" goto formats
if "%choice%"=="5" goto end

echo 无效选项，请重新选择
timeout /t 2 >nul
goto menu

:example
cls
echo 运行交互式示例...
python example.py
pause
goto menu

:single
cls
echo 下载单个视频字幕
echo -----------------
set /p url=请输入视频URL: 
if "%url%"=="" (
    echo URL不能为空！
    pause
    goto menu
)
python enhanced_bilisub.py -i "%url%"
pause
goto menu

:batch
cls
echo 批量下载视频字幕
echo -----------------
echo 请创建一个文本文件，每行包含一个视频URL
echo.
set /p file=请输入文本文件路径 (例如: urls.txt): 
if "%file%"=="" (
    echo 文件路径不能为空！
    pause
    goto menu
)
if not exist "%file%" (
    echo 文件 %file% 不存在！
    pause
    goto menu
)
python enhanced_bilisub.py -i "%file%" -c 3
pause
goto menu

:formats
cls
echo 生成多种格式字幕
echo -----------------
set /p url=请输入视频URL: 
if "%url%"=="" (
    echo URL不能为空！
    pause
    goto menu
)
python enhanced_bilisub.py -i "%url%" -f srt,ass,vtt,json
pause
goto menu

:end
echo 感谢使用哔哩哔哩字幕下载工具！
timeout /t 2 >nul
exit /b 0