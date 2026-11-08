#!/bin/bash
# 在 WSL 内准备 Mu-Silicium 构建：复制源码 + 拉取 submodule（走镜像）
set -e

SRC=/mnt/c/Users/Administrator/WorkBuddy/2026-10-29-20-41-12/Mu-Silicium
WORK=/root/work
DST=$WORK/Mu-Silicium

export GIT_CONFIG_GLOBAL=/root/.gitconfig
git config --global url."https://gh-proxy.com/https://github.com/".insteadOf "https://github.com/"
git config --global url."https://gh-proxy.com/https://github.com".insteadOf "https://github.com"
git config --global http.postBuffer 524288000
git config --global advice.detachedHead false

echo "===> 1. 复制源码到 WSL 内部（ext4，编译快）"
mkdir -p "$WORK"
if [ ! -d "$DST" ]; then
  cp -a "$SRC" "$DST"
  echo "已复制 $(du -sh $DST | cut -f1)"
else
  echo "已存在，同步 lafaPkg"
  cp -a "$SRC/Platforms/Realme/lafaPkg" "$DST/Platforms/Realme/" 2>/dev/null || true
fi
cd "$DST"

echo "===> 2. 初始化轻量 submodule（Mu_Basecore / Common / openssl / ACPI）"
git submodule update --init --depth 1 \
  Mu_Basecore Common/Mu Common/Mu_OEM_Sample Silicium-ACPI \
  Silicon/Silicium/OpensslPkg/Library/OpensslLib/openssl 2>&1 | tail -5

echo "===> 3. Binaries：sparse checkout，仅取 infiniti（同 SM8850 复用）"
if [ ! -d Binaries/.git ] && [ ! -f Binaries/.git ]; then
  rm -rf Binaries
  git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/Project-Silicium/Device-Binaries.git Binaries
  cd Binaries
  git sparse-checkout set infiniti
  cd ..
fi

echo "===> 4. 结果确认"
{
  echo "Mu-Silicium: $(du -sh . | cut -f1)"
  echo "Binaries/infiniti: $(du -sh Binaries/infiniti 2>/dev/null | cut -f1 || echo MISSING)"
  echo "Mu_Basecore: $(ls Mu_Basecore | head -3 | tr '\n' ' ')"
  echo "Common/Mu: $(ls Common/Mu 2>/dev/null | head -3 | tr '\n' ' ')"
  ls -d Binaries/infiniti/QcomPkg/Drivers 2>/dev/null && echo "QcomPkg drivers OK"
} | tee /tmp/uefi-prep.log

echo "===> 完成"
