#!/usr/bin/env python3
"""从 Android vendor_boot.img (header v3/v4) 中提取 dtb。"""
import struct
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])

data = src.read_bytes()
magic = data[:8]
print('magic:', magic)
if magic != b'VNDRBOOT':
    raise SystemExit('不是 vendor_boot 镜像')

header_version = struct.unpack_from('<I', data, 8)[0]
page_size = struct.unpack_from('<I', data, 12)[0]
vendor_ramdisk_size = struct.unpack_from('<I', data, 24)[0]
header_size = struct.unpack_from('<I', data, 2096)[0]
dtb_size = struct.unpack_from('<I', data, 2100)[0]
dtb_addr = struct.unpack_from('<Q', data, 2104)[0]

# vendor_ramdisk_table 相关字段仅 v4 有
vrt_size = struct.unpack_from('<I', data, 2112)[0] if header_version >= 4 else 0
bootconfig_size = struct.unpack_from('<I', data, 2124)[0] if header_version >= 4 else 0

print(f'header_version : {header_version}')
print(f'page_size      : {page_size}')
print(f'header_size    : {header_size}')
print(f'vendor_ramdisk : {vendor_ramdisk_size} bytes')
print(f'dtb_size       : {dtb_size} bytes')
print(f'dtb_addr       : {dtb_addr:#x}')
if header_version >= 4:
    print(f'vrt_size       : {vrt_size}')
    print(f'bootconfig_size: {bootconfig_size}')
print(f'file size      : {len(data)}')


def align(n, p):
    return (n + p - 1) // p * p


dtb_offset = align(header_size, page_size) + align(vendor_ramdisk_size, page_size)
print(f'dtb_offset     : {dtb_offset} ({dtb_offset:#x})')

if dtb_size == 0:
    raise SystemExit('dtb_size 为 0')

dtb = data[dtb_offset:dtb_offset + dtb_size]
print(f'提取长度       : {len(dtb)}')
print(f'dtb magic      : {dtb[:4].hex()}  期望 d00dfeed')

if dtb[:4] != b'\xd0\x0d\xfe\xed':
    # 搜索整个文件里的 FDT magic 作为兜底
    print('头部不是 FDT magic，全文件搜索...')
    idx = data.find(b'\xd0\x0d\xfe\xed')
    if idx < 0:
        raise SystemExit('未找到 FDT magic')
    total = struct.unpack_from('>I', data, idx + 4)[0]
    dtb = data[idx:idx + total]
    print(f'在偏移 {idx} 找到 FDT，总长 {total}')

dst.write_bytes(dtb)
print(f'已写入 {dst} ({len(dtb)} bytes)')
