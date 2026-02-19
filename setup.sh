#!/bin/bash
# Talker-Thinker 环境设置脚本

set -e

echo "=== Talker-Thinker 环境设置 ==="

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "检测到 Python 版本: $PYTHON_VERSION"

# 删除旧的虚拟环境（如果存在）
if [ -d ".venv" ]; then
    echo "正在删除旧的虚拟环境..."
    rm -rf .venv
fi

# 创建虚拟环境
echo "正在创建虚拟环境..."
python3 -m venv .venv
echo "虚拟环境创建成功"

# 激活虚拟环境
echo "正在激活虚拟环境..."
source .venv/bin/activate

# 在虚拟环境中配置镜像源
echo "正在配置 pip 镜像源（清华源）..."
mkdir -p .venv/pip.conf.d
cat > .venv/pip.conf << 'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
EOF
export PIP_CONFIG_FILE=.venv/pip.conf

# 升级 pip
echo "正在升级 pip..."
pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

# 安装依赖
echo "正在安装依赖..."
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

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
