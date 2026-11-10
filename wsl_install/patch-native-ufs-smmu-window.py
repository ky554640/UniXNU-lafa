#!/usr/bin/env python3
"""Widen the NativeUfs SMMU window from sheng's SM8550 size to SM8850's.

sheng's apps_smmu register file fits in 0xd0000 bytes (SM8550), but lafa's
(SM8850, qcom,qsmmu-v500) apps_smmu has 128 global pages + 81 context banks, so
its register file is 0xd1000 bytes and lives in a 0x100000 (1 MiB) window, per
the board DT (apps-smmu@15000000 reg = 0x15000000 size 0x100000) and the Data A
Live SM8850 port (Sm8850.h, QcomUsbBypass.c).

With sheng's 0xd0000 bound, planUfsSmmu reads the geometry and returns
"unsupported SMMU geometry" (slot stays 0xffffffff), which is the panic seen on
lafa. Widen the map and the geometry checks to 0x100000.

This patches three sites in drivers/NativeUfs:
- NativeUfs.cpp smmuBypassStream() mapPhys 0xd0000 -> 0x100000
- NativeUfs.cpp inspectContextBanks() mapPhys + geometry check 0xd0000 -> 0x100000
- SmmuTakeover.h planUfsSmmuBank() geometry check 0xd0000 -> 0x100000

Idempotent; use --check to verify.
"""
import argparse
import sys
from pathlib import Path


def patch_file(path: Path, check_only: bool) -> int:
    text = path.read_text()
    n = text.count("0xd0000")
    if n == 0:
        return 0
    if not check_only:
        text = text.replace("0xd0000", "0x100000")
        path.write_text(text)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("native_ufs_dir", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files = [args.native_ufs_dir / "NativeUfs.cpp",
             args.native_ufs_dir / "SmmuTakeover.h",
             args.native_ufs_dir / "tests" / "SmmuTakeover.cpp"]
    total = 0
    for f in files:
        if not f.is_file():
            continue
        n = patch_file(f, args.check)
        if n:
            print(f"{f.name}: {'would replace' if args.check else 'replaced'} {n} x 0xd0000 -> 0x100000")
        total += n
    if args.check:
        if total == 0:
            print("applied")
            sys.exit(0)
        else:
            print(f"{total} site(s) still use 0xd0000")
            sys.exit(1)


if __name__ == "__main__":
    main()
