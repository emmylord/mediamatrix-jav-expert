#!/usr/bin/env bash
# JAV Expert 插件依赖安装脚本
# 在 MediaMatrix 根目录的 venv 激活后执行一次即可

set -e

echo "[jav_expert] 安装依赖..."
pip install "httpx>=0.27" "curl_cffi>=0.7" beautifulsoup4 lxml
echo "[jav_expert] 依赖安装完成"
