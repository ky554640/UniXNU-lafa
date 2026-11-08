# Patches against upstream

This directory holds the lafa (realme GT8 Pro, SM8850) bring-up changes that
cannot live in `board.toml` because they patch the upstream UEFI firmware
(`UniXNU/uefi-sheng`) and the shared `UniXNU` package.

The upstream checkout that these patches target is pinned by `upstream.rev` at
the repository root.

## mu-silicium/embed-payload.patch

Implements the embedded-payload hand-off that the GKI-2.0 device needs. The
stock ABL on this board ignores the `boot.img` ramdisk field, so the payload FAT
volume must be carried inside the kernel image and handed to UEFI by the
firmware itself. The patch adds, end to end:

1. `BootShim/BootShim.S` — a `LOAD_BASE`/`text_offset` distinct from `FD_BASE`
   so the boot loader places the combined `shim + firmware + payload` image in
   the reserved *Kernel* window (`0xC7800000`) instead of clobbering the
   SEC/DXE heaps that sit right after the firmware run address. The payload is
   left in place (not copied) and its address/size are passed to SEC in
   `x1`/`x2`.
2. `SiliciumPkg.dec` — `gSiliciumPayloadHobGuid`.
3. `Sec/AArch64/ModuleEntryPoint.S` — save `x1`/`x2` into `gSecPayloadBase` /
   `gSecPayloadSize` before the cache maintenance.
4. `Sec/Sec.c` + `Sec/Sec.inf` — publish a `{ Base, Size }` payload HOB.
5. `UniXNURamDiskDxe` (see `unixnu/` below) — consume that HOB and publish the
   payload as a block device.

Apply with `git apply` against a checkout of `UniXNU/uefi-sheng` at
`upstream.rev`.

## unixnu/

Two files changed in the shared `UniXNU` package, stored as full copies because
the local UniXNU clone has no usable git baseline:

- `UniXNULib-Main.c` — mirror `UniXNULog` lines to `gST->ConOut` so the boot
  log is visible on the panel (the board has no reachable UART). Replaces
  `package/UniXNUPkg/Library/UniXNULib/Main.c`.
- `UniXNURamDiskDxe.c` — read the SEC payload HOB (same GUID as
  `gSiliciumPayloadHobGuid`) and publish it as a block device, taking priority
  over the FDT `linux,initrd-*` path. Replaces
  `package/UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.c`.

## Related build tooling

- `wsl_install/build-uefi.sh` — syncs `BootShim/` and `Silicon/SiliciumPkg/`
  (not just `lafaPkg/`) into the WSL build tree, applies
  `patch-exception-dump.py`, and exports `FVMAIN.Fv` for audit.
- `wsl_install/patch-exception-dump.py` — trims the EDK2 exception dump (drops
  the V0–V31 lines, shrinks the stack window) so the console log stays on the
  panel.
- `wsl_install/patch-bootimg-loadbase.py` — adds `load_base` support to the
  pinned `bootimg.py` so `[bootimg] load_base` drives the ARM64 `text_offset`.
- `tools/audit-fd.py` — pre-boot safety audit; refuses to proceed if a
  forbidden storage/PMIC driver is still linked.
