#!/bin/bash
# 把 CI 下载的 artifact 打成能上机的 boot.img。
#
# 用法:
#   bash repack_payload.sh lafa-xnu-1.zip
#   bash repack_payload.sh payload.img          # 也可以直接给已解压的 payload
#
# 产物: out_lafa/boot.img + boot.json
#
# 注意：实际打包在 WSL 里做（mk-bootimg.sh 需要 rsync、edk2 构建树和 /mnt/c 路径），
# 所以这里只负责准备输入，然后把 WSL 路径交给它。
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
WORK="$SRC/out_lafa/ci"

# /c/Users/... -> /mnt/c/Users/...
WSRC=$(printf '%s' "$SRC" | sed 's|^/\([A-Za-z]\)/|/mnt/\1/|')

[ $# -ge 1 ] || { echo "用法: bash repack_payload.sh <artifact.zip|payload.img>"; exit 1; }
[ -f "$1" ] || { echo "文件不存在: $1"; exit 1; }

case "$1" in
  *.zip)
    rm -rf "$WORK"; mkdir -p "$WORK"
    echo "== 解压 $(basename "$1") =="
    python3 -c "import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$1" "$WORK"
    PAYLOAD=$(find "$WORK" -name "payload.img" -type f | head -1)
    ;;
  *.gz)
    mkdir -p "$WORK"
    echo "== 解压 $(basename "$1") =="
    gzip -dc "$1" > "$WORK/payload.img"
    PAYLOAD="$WORK/payload.img"
    ;;
  *)
    PAYLOAD="$1"
    ;;
esac

[ -n "${PAYLOAD:-}" ] && [ -f "$PAYLOAD" ] || {
  echo "找不到 payload.img，内容如下："; find "$WORK" -type f 2>/dev/null | head -20; exit 1; }

PAYLOAD_WSL=$(printf '%s' "$(cd "$(dirname "$PAYLOAD")" && pwd)/$(basename "$PAYLOAD")" | sed 's|^/\([A-Za-z]\)/|/mnt/\1/|')

echo "== payload: $PAYLOAD_WSL =="
ls -l "$PAYLOAD"
echo
echo "== 在 WSL 里重打包 boot.img（带 ramdisk）=="
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -e bash -c "bash '$WSRC/wsl_install/mk-bootimg.sh' '$PAYLOAD_WSL'"

echo
echo "== 产物 =="
ls -l "$SRC/out_lafa/" 2>/dev/null
echo
echo "上机: bash boot_uefi_ram.sh   （脚本按 out_lafa/boot.img 引导）"
