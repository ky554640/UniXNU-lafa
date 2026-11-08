#!/bin/bash
# 打包 lafa boot.img：gzip(BootShim + UEFI FD) + 原厂 DTB [+ payload ramdisk]
#
# 用法:
#   bash mk-bootimg.sh                    # 无 payload（只验证 UEFI 本体）
#   bash mk-bootimg.sh <payload.img>      # 带 payload（CI 产物 out/lafa/payload/payload.img）
set -e

SRC=/mnt/c/Users/Administrator/WorkBuddy/2026-10-29-20-41-12
W=/root/work
RAMDISK=none

# 允许传 Windows 路径（C:/... 或 C:\...），转成 WSL 路径
if [ $# -ge 1 ] && [ -n "$1" ]; then
  src="$1"
  case "$src" in
    [A-Za-z]:[\\/]*) drive=$(printf '%s' "${src:0:1}" | tr 'A-Z' 'a-z'); src="/mnt/$drive/$(printf '%s' "${src:2}" | tr '\\' '/')" ;;
  esac
  [ -f "$src" ] || { echo "payload 不存在: $1 -> $src"; exit 1; }
  RAMDISK="file"
  PAYLOAD="$src"
fi

echo "===> 1. 同步 UniXNU（含 scripts/package/profiles）"
rsync -a --exclude '.git' --exclude 'out' "$SRC/UniXNU/" "$W/UniXNU/"

echo "===> 2. 同步设备仓库"
rsync -a --exclude '.git' --exclude '.cache' --exclude 'out' "$SRC/UniXNU-lafa/" "$W/UniXNU-lafa/"

echo "===> 3. 同步原厂 DTB"
cp "$SRC/lafa_vendor.dtb" "$W/lafa_vendor.dtb"

echo "===> 4. 打包 boot.img（ramdisk: $RAMDISK${PAYLOAD:+ $PAYLOAD}）"
mkdir -p "$W/out/lafa"
cd "$W/UniXNU"
set +e
if [ "$RAMDISK" = file ]; then
  cp "$PAYLOAD" "$W/out/lafa/payload.img"
  python3 unixnu bootimg \
    -D "$W/UniXNU-lafa" \
    --uefi "$W/Mu-Silicium" \
    --dtb "$W/lafa_vendor.dtb" \
    --ramdisk "$W/out/lafa/payload.img" \
    -o "$W/out/lafa/boot.img" 2>&1 | tail -40
else
  python3 unixnu bootimg \
    -D "$W/UniXNU-lafa" \
    --uefi "$W/Mu-Silicium" \
    --dtb "$W/lafa_vendor.dtb" \
    --ramdisk none \
    -o "$W/out/lafa/boot.img" 2>&1 | tail -40
fi
RC=${PIPESTATUS[0]}
set -e
echo "===> bootimg 退出码: $RC"
ls -lh "$W/out/lafa/boot.img" 2>/dev/null || echo "(未生成 boot.img)"

echo "===> 5. 导出到 Windows 侧 out_lafa/"
mkdir -p "$SRC/out_lafa"
cp -f "$W/out/lafa/boot.img" "$SRC/out_lafa/boot.img" 2>/dev/null || true
cp -f "$W/out/lafa/boot.json" "$SRC/out_lafa/boot.json" 2>/dev/null || true
ls -l "$SRC/out_lafa/boot.img" 2>/dev/null || true
