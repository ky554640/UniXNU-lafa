#!/bin/bash
# UniXNU 构建环境初始化（Ubuntu 24.04 on WSL2）
set -e

export DEBIAN_FRONTEND=noninteractive

echo "===> 1. 配置 apt 源（清华镜像，先用 http 因 base 镜像无 CA 证书）"
rm -f /etc/apt/sources.list.d/*.sources /etc/apt/sources.list
cat > /etc/apt/sources.list <<'EOF'
deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble main restricted universe multiverse
deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble-updates main restricted universe multiverse
deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble-backports main restricted universe multiverse
deb http://mirrors.tuna.tsinghua.edu.cn/ubuntu/ noble-security main restricted universe multiverse
EOF

echo "===> 2. 更新索引"
apt-get update -qq

echo "===> 2b. 先装 CA 证书，随后切回 https"
apt-get install -y -qq --no-install-recommends ca-certificates
update-ca-certificates 2>/dev/null || true
sed -i 's|http://mirrors.tuna.tsinghua.edu.cn|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list
apt-get update -qq

echo "===> 3. 安装基础工具"
apt-get install -y -qq --no-install-recommends \
  ca-certificates curl wget gnupg lsb-release software-properties-common \
  git patch flex bison bzip2 cpio rsync unzip zip \
  tcsh unifdef cmake lld mtools build-essential pkg-config ninja-build \
  python3 python3-dev python3-pip python3-venv \
  xz-utils zlib1g-dev libssl-dev libbsd-dev uuid-dev \
  device-tree-compiler liblz4-tool vim nano sudo file bc

echo "===> 4. 安装 LLVM/Clang"
apt-get install -y -qq --no-install-recommends clang llvm llvm-dev libclang-dev

echo "===> 5. 版本确认"
{
  echo "--- 环境 ---"
  echo "OS: $(. /etc/os-release && echo $PRETTY_NAME)"
  echo "Kernel: $(uname -r)"
  echo "CPU: $(nproc) cores"
  echo "Mem: $(free -h | awk '/Mem:/{print $2}')"
  echo "--- 工具 ---"
  echo "clang: $(clang --version | head -1)"
  echo "ld.lld: $(ld.lld --version 2>/dev/null | head -1 || echo MISSING)"
  echo "python3: $(python3 --version)"
  echo "git: $(git --version)"
  echo "cmake: $(cmake --version | head -1)"
  echo "ninja: $(ninja --version)"
  echo "mtools: $(mformat --version 2>&1 | head -1)"
  echo "dtc: $(dtc --version 2>&1 | head -1)"
  echo "lz4: $(lz4 --version 2>&1 | head -1)"
  echo "unifdef: $(unifdef -V 2>&1 | head -1 || echo ok)"
} | tee /tmp/env-report.txt

echo "===> 完成"
