#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
哔哩哔哩字幕处理API客户端示例
演示如何使用API接口处理字幕
"""
import os
import json
import time
import sys
import argparse
import requests
from urllib.parse import urljoin

# 默认API配置
DEFAULT_CONFIG = {
    "api_url": "http://localhost:8000",
    "api_key": "test_key",
}

class BiliSubAPIClient:
    """哔哩哔哩字幕处理API客户端"""
    
    def __init__(self, api_url, api_key):
        """初始化客户端
        
        Args:
            api_url: API服务器地址
            api_key: API密钥
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
    
    def create_task(self, video_url, credentials=None, output_formats=None, use_asr=True, 
                  asr_model="small", asr_lang="zh", callback_url=None):
        """创建字幕处理任务
        
        Args:
            video_url: B站视频URL
            credentials: B站账号凭证字典(可选)
            output_formats: 输出格式列表
            use_asr: 是否使用语音识别
            asr_model: 语音识别模型大小
            asr_lang: 语音识别语言
            callback_url: 回调通知URL
            
        Returns:
            任务信息字典
        """
        # 准备请求数据
        payload = {
            "url": video_url,
            "use_asr": use_asr,
            "asr_model": asr_model,
            "asr_lang": asr_lang,
        }
        
        # 添加可选参数
        if credentials:
            payload["credentials"] = credentials
        
        if output_formats:
            payload["output_formats"] = output_formats
        else:
            payload["output_formats"] = ["srt"]
            
        if callback_url:
            payload["callback_url"] = callback_url
        
        # 发送请求
        response = requests.post(
            f"{self.api_url}/api/tasks",
            headers=self.headers,
            json=payload
        )
        
        # 检查响应
        if response.status_code != 200:
            error_msg = response.json().get("detail", f"HTTP错误: {response.status_code}")
            raise Exception(f"创建任务失败: {error_msg}")
        
        return response.json()
    
    def get_task_status(self, task_id):
        """获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态信息字典
        """
        response = requests.get(
            f"{self.api_url}/api/tasks/{task_id}",
            headers=self.headers
        )
        
        # 检查响应
        if response.status_code != 200:
            error_msg = response.json().get("detail", f"HTTP错误: {response.status_code}")
            raise Exception(f"获取任务状态失败: {error_msg}")
        
        return response.json()
    
    def get_task_result(self, task_id):
        """获取任务结果
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务结果信息字典
        """
        response = requests.get(
            f"{self.api_url}/api/tasks/{task_id}/result",
            headers=self.headers
        )
        
        # 检查响应
        if response.status_code != 200:
            error_msg = response.json().get("detail", f"HTTP错误: {response.status_code}")
            raise Exception(f"获取任务结果失败: {error_msg}")
        
        return response.json()
    
    def download_file(self, file_url, output_path):
        """下载字幕文件
        
        Args:
            file_url: 文件URL (相对路径)
            output_path: 保存路径
            
        Returns:
            文件保存路径
        """
        full_url = urljoin(self.api_url, file_url)
        
        response = requests.get(
            full_url,
            headers=self.headers,
            stream=True
        )
        
        # 检查响应
        if response.status_code != 200:
            error_msg = response.json().get("detail", f"HTTP错误: {response.status_code}")
            raise Exception(f"下载文件失败: {error_msg}")
        
        # 保存文件
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return output_path
        
    def wait_for_task(self, task_id, poll_interval=2.0, timeout=None):
        """等待任务完成
        
        Args:
            task_id: 任务ID
            poll_interval: 轮询间隔(秒)
            timeout: 超时时间(秒)
            
        Returns:
            任务状态信息字典
        """
        start_time = time.time()
        while True:
            # 检查超时
            if timeout and (time.time() - start_time > timeout):
                raise TimeoutError(f"等待任务完成超时: {task_id}")
            
            # 获取任务状态
            status = self.get_task_status(task_id)
            
            # 打印进度
            progress = status.get("progress", 0)
            print(f"任务进度: {progress:.1f}% - 状态: {status['status']}", end='\r')
            
            # 检查任务是否已完成或失败
            if status["status"] == "completed":
                print("\n任务已完成")
                return status
            elif status["status"] == "failed":
                print(f"\n任务失败: {status.get('error', '未知错误')}")
                return status
            
            # 等待一段时间再次检查
            time.sleep(poll_interval)

def read_config(config_file):
    """从配置文件读取API配置
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        配置字典
    """
    if not os.path.exists(config_file):
        return {}
    
    with open(config_file, 'r') as f:
        return json.load(f)

def main():
    """客户端主函数"""
    parser = argparse.ArgumentParser(description="哔哩哔哩字幕处理API客户端")
    parser.add_argument("-u", "--url", required=True, help="B站视频URL")
    parser.add_argument("-k", "--api-key", help="API密钥")
    parser.add_argument("-s", "--server", help="API服务器地址")
    parser.add_argument("-f", "--formats", default="srt", help="输出格式，用逗号分隔")
    parser.add_argument("-o", "--output", default="downloads", help="输出目录")
    parser.add_argument("--use-asr", action="store_true", default=True, help="使用语音识别")
    parser.add_argument("--no-asr", dest="use_asr", action="store_false", help="禁用语音识别")
    parser.add_argument("--config", help="API配置文件路径")
    
    args = parser.parse_args()
    
    # 加载配置
    config = DEFAULT_CONFIG.copy()
    if args.config:
        config.update(read_config(args.config))
    
    # 命令行参数覆盖配置文件
    if args.api_key:
        config["api_key"] = args.api_key
    if args.server:
        config["api_url"] = args.server
    
    # 创建输出目录
    os.makedirs(args.output, exist_ok=True)
    
    # 解析输出格式
    formats = [f.strip() for f in args.formats.split(",")]
    
    # 创建客户端
    client = BiliSubAPIClient(config["api_url"], config["api_key"])
    
    try:
        # 创建任务
        print(f"创建字幕处理任务: {args.url}")
        task = client.create_task(
            video_url=args.url,
            output_formats=formats,
            use_asr=args.use_asr
        )
        task_id = task["task_id"]
        print(f"任务已创建: {task_id}")
        
        # 等待任务完成
        print("等待任务处理...")
        status = client.wait_for_task(task_id)
        
        # 如果任务成功，下载结果
        if status["status"] == "completed":
            # 获取任务结果
            result = client.get_task_result(task_id)
            print(f"任务完成，生成了 {len(result['files'])} 个文件")
            
            # 下载文件
            for filename, url in result["download_urls"].items():
                output_path = os.path.join(args.output, filename)
                print(f"下载文件: {filename}")
                client.download_file(url, output_path)
                print(f"已保存到: {output_path}")
            
            print(f"\n所有文件已下载到: {os.path.abspath(args.output)}")
            
            # 显示统计信息
            stats = result["stats"]
            print("\n统计信息:")
            print(f"- 成功获取字幕: {stats.get('success', 0)}/{stats.get('total_videos', 0)}")
            if stats.get("asr_used", 0) > 0:
                print(f"- 使用语音识别: {stats.get('asr_used', 0)} 个视频")
        
    except Exception as e:
        print(f"错误: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()