#!/bin/bash
# Talker-Thinker 环境设置脚本

set -e

echo "=== Talker-Thinker 环境设置 ==="

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "检测到 Python 版本: $PYTHON_VERSION"

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "正在创建虚拟环境..."
    python3 -m venv .venv
    echo "虚拟环境创建成功"
else
    echo "虚拟环境已存在"
fi

# 激活虚拟环境
echo "正在激活虚拟环境..."
source .venv/bin/activate

# 升级 pip
echo "正在升级 pip..."
pip install --upgrade pip

# 安装依赖
echo "正在安装依赖..."
pip install -r requirements.txt

# 复制环境变量模板
if [ ! -f ".env" ]; then
    echo "正在复制环境变量模板..."
    cp .env.example .env
    echo "请编辑 .env 文件填入你的 API 密钥"
fi

echo ""
echo "=== 设置完成 ==="
echo ""
echo "使用以下命令激活环境:"
echo "  source .venv/bin/activate"
echo ""
echo "运行交互模式:"
echo "  python main.py -i"
echo ""
echo "退出虚拟环境:"
echo "  deactivate"
