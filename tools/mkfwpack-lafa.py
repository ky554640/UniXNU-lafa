#!/usr/bin/env python3
"""把 lafa (realme GT8 Pro) 的 GPU 固件打包成 PANDFW01 固件包。

用法:
  python3 tools/mkfwpack-lafa.py <固件源目录> [输出.img]

固件源目录应包含以下文件（从 lafa /vendor/firmware/ 提取）:
  gen80200_gmu.bin    -- GMU 固件
  gen80200_sqe.fw     -- SQE 固件
  gen80200_zap.mbn    -- ZAP 固件（PAS 认证用）

输出默认写到当前目录 lafa_fwpack.img，格式兼容 pandora_gpu.c / pandora_adsp.c 的
pandora_fw_read()（块 0 是 "PANDFW01" 头 + 目录项，之后是 4 KiB 对齐的文件体）。

依赖同目录的 mkfwpack.py（原始打包器）。
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MKFW = os.path.join(HERE, "mkfwpack.py")

# GPU 冷启动所需的固件（名称必须与 lafa_gpu.c 里 pandora_fw_read 查找的名字一致）
REQUIRED = [
    "gen80200_gmu.bin",
    "gen80200_sqe.fw",
    "gen80200_zap.mbn",
]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    srcdir = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "lafa_fwpack.img"

    if not os.path.isdir(srcdir):
        print(f"错误: 固件源目录不存在: {srcdir}", file=sys.stderr)
        sys.exit(1)

    files = []
    for name in REQUIRED:
        p = os.path.join(srcdir, name)
        if not os.path.isfile(p):
            print(f"警告: 缺少 {name}（跳过）", file=sys.stderr)
            continue
        files.append(p)

    if not files:
        print("错误: 源目录里一个 GPU 固件都没有找到。", file=sys.stderr)
        print("      请先从 lafa 的 /vendor/firmware/ 提取 gen80200_* 文件。", file=sys.stderr)
        sys.exit(1)

    print(f"打包 {len(files)} 个固件 -> {out}")
    for f in files:
        print(f"  {os.path.basename(f)}  ({os.path.getsize(f)} bytes)")
    subprocess.check_call([sys.executable, MKFW, out] + files)
    print(f"完成: {out}")


if __name__ == "__main__":
    main()
