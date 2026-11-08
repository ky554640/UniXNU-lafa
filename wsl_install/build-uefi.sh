#!/bin/bash
# 手动驱动 EDK II 构建 lafa UEFI 固件（复刻 unixnu firmware 步骤，绕开损坏的 .git）
set -e

SRC=/mnt/c/Users/Administrator/WorkBuddy/2026-10-29-20-41-12
W=/root/work
UEFI=$W/Mu-Silicium
EDK2=$UEFI/Mu_Basecore
TREE=$W/tree
CONF=$W/edk2-conf
OUT=$W/out

echo "===> 1. 同步修改过的集成文件"
rsync -a --delete "$SRC/Mu-Silicium/Platforms/Realme/lafaPkg/" "$UEFI/Platforms/Realme/lafaPkg/"
cp "$SRC/Mu-Silicium/Resources/Configs/lafa.toml" "$UEFI/Resources/Configs/"
# SEC (the embedded-payload HOB) and BootShim (the payload handoff) live outside
# the board package, so they need an explicit sync too.
rsync -a --delete "$SRC/Mu-Silicium/Silicon/Silicium/SiliciumPkg/" "$UEFI/Silicon/Silicium/SiliciumPkg/"
rsync -a --delete "$SRC/Mu-Silicium/BootShim/" "$UEFI/BootShim/"

echo "===> 2. 准备 UniXNU 模块源（package + DarwinBoot）"
rm -rf "$TREE"
mkdir -p "$TREE/drivers"
# Always resync: local patches to UniXNULib (the on-screen log mirror) have to
# reach the firmware volume, and a one-shot "copy if missing" would ignore them.
mkdir -p "$W/UniXNU"
rsync -a --delete --exclude '.git' "$SRC/UniXNU/package" "$W/UniXNU/"
mkdir -p "$W/UniXNU/drivers"
rsync -a --delete --exclude '.git' "$SRC/UniXNU/drivers/DarwinBoot" "$W/UniXNU/drivers/"
ln -sfn "$W/UniXNU/package" "$TREE/package"
ln -sfn "$W/UniXNU/drivers/DarwinBoot" "$TREE/drivers/DarwinBoot"

echo "===> 2b. 缩小异常 dump（给启动日志留屏幕空间）"
python3 "$SRC/wsl_install/patch-exception-dump.py" \
  "$UEFI/Mu_Basecore/UefiCpuPkg/Library/CpuExceptionHandlerLib/AArch64/CpuExceptionHandlerLib.c" || exit 1

echo "===> 3. 编译 BaseTools（首次较慢）"
TOOLS=$EDK2/BaseTools
if [ ! -f "$TOOLS/Source/C/bin/GenFw" ]; then
  # make 对部分子目录会返回非零（历史遗留），以产物是否存在为准
  make -C "$TOOLS/Source/C" -j"$(nproc)" > "$W/basetools.log" 2>&1 || true
  if [ ! -f "$TOOLS/Source/C/bin/GenFw" ]; then
    echo "BaseTools 编译失败，末尾日志："; tail -25 "$W/basetools.log"; exit 1
  fi
fi
echo "BaseTools OK: $(ls "$TOOLS/Source/C/bin" | wc -l) tools"

echo "===> 4. 初始化 EDK2 配置"
mkdir -p "$CONF"
for n in target tools_def build_rule; do
  [ -f "$CONF/$n.txt" ] || cp "$TOOLS/Conf/$n.template" "$CONF/$n.txt"
done

echo "===> 5. 构建 lafa UEFI（DEBUG/CLANGPDB）"
PACKAGES_PATH="$UEFI:$UEFI/Platforms/Realme:$TREE/package:$TREE/drivers/DarwinBoot:$EDK2:$UEFI/Common/Mu:$UEFI/Common/Mu_OEM_Sample:$UEFI/Silicon/Qualcomm:$UEFI/Silicon/Silicium"
export WORKSPACE="$UEFI"
export EDK_TOOLS_PATH="$TOOLS"
export CONF_PATH="$CONF"
export PACKAGES_PATH
export PYTHON_COMMAND=python3
export PATH="$TOOLS/BinWrappers/PosixLike:$TOOLS/Source/C/bin:$PATH"
export SOURCE_DATE_EPOCH=$(git -C "$UEFI" log -1 --format=%ct 2>/dev/null || echo 1730000000)

mkdir -p "$OUT"
cd "$UEFI"
set +e
build -p Platforms/Realme/lafaPkg/lafa.dsc -a AARCH64 -b DEBUG -t CLANGPDB -n "$(nproc)" \
  -D FD_BASE=0xC6900000 -D FD_SIZE=0x300000 -D FD_BLOCKS=768 \
  -D DEVICE_MODEL=lafa -D ENABLE_SECUREBOOT=0 -D MEMORY_PROTECTION=TRUE \
  -D SHIP_MODE=FALSE -D BUILDID_STRING=lafa-unixnu-20261101 \
  > "$OUT/firmware.log" 2>&1
RC=$?
set -e

echo "===> build 退出码: $RC"
echo "--- 日志末尾 ---"
tail -40 "$OUT/firmware.log"

FD=$(find "$UEFI/Build" -name "SILICIUM_UEFI.fd" 2>/dev/null | head -1)
if [ -n "$FD" ] && [ -s "$FD" ]; then
  echo "=== FD 产物: $FD ($(stat -c%s "$FD") 字节) ==="
  # Export the uncompressed volume next to it: tools/audit-fd.py greps the module
  # names inside it, and the FD itself is LZMA compressed.
  mkdir -p "$SRC/out_lafa"
  cp -f "$FD" "$SRC/out_lafa_fd.img" 2>/dev/null || true
  FVM=$(dirname "$FD")/FVMAIN.Fv
  [ -f "$FVM" ] && cp -f "$FVM" "$SRC/out_lafa/FVMAIN.Fv" 2>/dev/null || true
else
  echo "=== 未生成 FD ==="
fi
exit $RC
