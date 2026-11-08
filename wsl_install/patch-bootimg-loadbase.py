import sys

p = sys.argv[1]
s = open(p).read()

# 1. compile_shim 签名加 load_base
old_sig = "def compile_shim(uefi, base, size, requires_header, scratch, payload_size=0):"
new_sig = "def compile_shim(uefi, base, size, requires_header, scratch, payload_size=0, load_base=None):"
assert old_sig in s, "sig not found"
s = s.replace(old_sig, new_sig)

# 2. clang 编译参数加 -DLOAD_BASE
old_run = "    run([clang, '--target=aarch64-none-elf', '-c', f'-DFD_BASE={base}', f'-DFD_SIZE={size}',\n         f'-DEMBEDDED_PAYLOAD_SIZE={payload_size}',\n         f'-DREQUIRES_KERNEL_HEADER={int(requires_header)}', source, '-o', obj], capture=True)"
new_run = "    cmd = [clang, '--target=aarch64-none-elf', '-c', f'-DFD_BASE={base}', f'-DFD_SIZE={size}',\n           f'-DEMBEDDED_PAYLOAD_SIZE={payload_size}',\n           f'-DREQUIRES_KERNEL_HEADER={int(requires_header)}']\n    if load_base:\n        cmd.append(f'-DLOAD_BASE={load_base}')\n    cmd += [source, '-o', obj]\n    run(cmd, capture=True)"
assert old_run in s, "run not found"
s = s.replace(old_run, new_run)

# 3. ARM64 头校验 text_offset 用 load_base
old_chk = "    if requires_header and (shim[56:60] != b'ARM\\x64' or struct.unpack_from('<QQ', shim, 8) != (base, len(shim) + size + payload_size)):\n        raise Error('the ARM64 image header does not describe the shim, firmware and embedded payload')"
new_chk = "    text_off = load_base if load_base else base\n    if requires_header and (shim[56:60] != b'ARM\\x64' or struct.unpack_from('<QQ', shim, 8) != (text_off, len(shim) + size + payload_size)):\n        raise Error('the ARM64 image header does not describe the shim, firmware and embedded payload')"
assert old_chk in s, "chk not found"
s = s.replace(old_chk, new_chk)

open(p, "w").write(s)
print("OK: compile_shim patched for load_base")
