#!/usr/bin/env python3
"""Exit the UniPro link's HIBERN8 power state before the first UFS transfer.

sheng's NativeUfs assumes the SM8550 bootloader hands over with the UniPro link
already up, so its hostBringUp() goes straight from hostStartQueue() to the
first NOP OUT. On SM8850 (lafa, realme GT8 Pro) the bootloader hands over with
the link in HIBERN8 (all M-PHY TX/RX FSMs = 1, auto-hibernate AHIT = 0), so no
transfer command ever leaves the host: the doorbell stays set and the NOP OUT
OCS times out to 0xf. That is exactly the panic seen on lafa:

    NATIVE_UFS root check: bring-up failed: NOP OUT @NativeUfs.cpp:1980

The fix is the same DME_HIBERNATE_EXIT sequence Data A Live uses on the 17 Pro
(SM8850, pandora): the register facts and the working sequence are in
refs/data-a-live-main/xnu/patches/0118-pandora-ufs-hibern8-exit.patch and the
hand-over state is recorded in refs/data-a-live-main/device/DT_FINDINGS.md
("handover with the UniPro link in HIBERN8 ... a request never leaves the
host").

This patch adds to drivers/NativeUfs/NativeUfs.cpp:

1. uicHibern8Exit(): DME_HIBERNATE_EXIT over the UIC command register
   (UFSHCI 0x90 UICCMD / 0x94 ARG1 / 0x98 ARG2 / 0x9c ARG3), wait for IS.UCCS
   (bit 10), check the result code in ARG2[7:0], wait for IS.UHXS (bit 5) and
   require HCS.UPMCRS (bits 10:8) == 1 (PWR_LOCAL). Returns bool, no panic.

2. hostBringUp() calls it after hostStartQueue() and before the NOP OUT.

Idempotent; use --check to verify.
"""
import argparse
import sys
from pathlib import Path

# The UIC command registers (UFSHCI standard, identical on SM8550/SM8850):
#   UICCMD 0x90, UICCMDARG1 0x94, UICCMDARG2 0x98, UICCMDARG3 0x9c
#   IS.UCCS = 1<<10, IS.UHXS = 1<<5, HCS.UCRDY = 1<<3, HCS.UPMCRS = bits 10:8
#   DME_HIBERNATE_EXIT = 0x18
HIBERN8_FN = r'''
// The SM8850 bootloader hands the UFS controller over with the UniPro link in
// HIBERN8 (all M-PHY TX/RX FSMs = 1) and auto-hibernate off (AHIT = 0), so no
// transfer command ever leaves the host: the doorbell stays set and the OCS
// times out. Wake the link the way Linux does (ufshcd_uic_hibern8_exit):
// DME_HIBERNATE_EXIT over UICCMD, wait for IS.UCCS, then IS.UHXS, and require
// HCS.UPMCRS == PWR_LOCAL. Link layer only: no UFS command, no data.
static bool uicHibern8Exit (void)
{
  const uintptr_t hc = gHost.hc;
  if (!hc) {
    return false;
  }
  if (!(read32 (hc, 0x30) & (1U << 3))) {          // HCS.UCRDY
    return false;
  }
  // Clear UIC-command-complete and hibernate-exit status, then issue the DME.
  write32 (hc, 0x20, (1U << 10) | (1U << 5));       // IS.UCCS | IS.UHXS (W1C)
  write32 (hc, 0x94, 0);                            // UICCMDARG1
  write32 (hc, 0x98, 0);                            // UICCMDARG2
  write32 (hc, 0x9c, 0);                            // UICCMDARG3
  write32 (hc, 0x90, 0x18);                         // DME_HIBERNATE_EXIT
  __asm__ volatile ("dsb sy" ::: "memory");

  unsigned loops = 100000;
  while (!(read32 (hc, 0x20) & (1U << 10)) && loops--) {  // wait IS.UCCS
    IODelay (1);
  }
  if (!(read32 (hc, 0x20) & (1U << 10))) {
    return false;                                    // UIC command never completed
  }
  const uint32_t rc = read32 (hc, 0x98) & 0xff;      // UICCMDARG2 result code
  write32 (hc, 0x20, (1U << 10));                    // clear IS.UCCS
  if (rc) {
    return false;
  }
  loops = 500000;
  while (!(read32 (hc, 0x20) & (1U << 5)) && loops--) {   // wait IS.UHXS
    IODelay (1);
  }
  if (!(read32 (hc, 0x20) & (1U << 5))) {
    return false;
  }
  write32 (hc, 0x20, (1U << 5));                     // clear IS.UHXS
  const uint32_t upmcrs = (read32 (hc, 0x30) >> 8) & 7;  // HCS.UPMCRS
  return upmcrs == 1;                                // PWR_LOCAL
}

'''

# hostBringUp(): wake the link after the queue is running, before the NOP OUT.
# Upstream text (2-space indent, no blank line between hostStartQueue and the
# stage assignment):
#   hostSlotsUpgrade (regionSlots, entries, wide);
#   if (!hostStartQueue (why)) return false;
#   gRootDiagnostic.stage = "NOP OUT";
ANCHOR_HOSTBRINGUP_NOP = (
    "  if (!hostStartQueue (why)) return false;\n"
    "  gRootDiagnostic.stage = \"NOP OUT\";"
)
HOSTBRINGUP_NOP_NEW = (
    "  if (!hostStartQueue (why)) return false;\n"
    "  if (!uicHibern8Exit ()) {\n"
    "    *why = \"hibernate exit\";\n"
    "    return false;\n"
    "  }\n"
    "  gRootDiagnostic.stage = \"NOP OUT\";"
)

# Fallback anchor: the stage assignment alone, in case the surrounding text differs.
ANCHOR_STAGE_NOP = "gRootDiagnostic.stage = \"NOP OUT\";"


def patch(path: Path, check_only: bool) -> bool:
    text = path.read_text()
    changed = False

    # 1. Insert the function (idempotent by the unique signature).
    if "static bool uicHibern8Exit" not in text:
        if check_only:
            print("uicHibern8Exit(): not applied")
            return False
        # Insert before hostBringUp. The upstream signature puts the brace on its
        # own line; the function is inserted just above it (after the comment block).
        anchor = "static bool hostBringUp (const char **why)\n{"
        if anchor not in text:
            print("anchor (hostBringUp) not found")
            return False
        text = text.replace(anchor, HIBERN8_FN + anchor, 1)
        changed = True
        print("uicHibern8Exit(): inserted")

    # 2. Call it in hostBringUp before the NOP OUT.
    if "uicHibern8Exit ()" not in text:
        if check_only:
            print("hostBringUp hibernate exit: not applied")
            return False
        if ANCHOR_HOSTBRINGUP_NOP in text:
            text = text.replace(ANCHOR_HOSTBRINGUP_NOP, HOSTBRINGUP_NOP_NEW, 1)
        elif ANCHOR_STAGE_NOP in text:
            # Insert the call right before the stage assignment.
            text = text.replace(
                ANCHOR_STAGE_NOP,
                "if (!uicHibern8Exit ()) {\n    *why = \"hibernate exit\";\n    return false;\n  }\n  "
                + ANCHOR_STAGE_NOP,
                1,
            )
        else:
            print("anchor (NOP OUT stage) not found")
            return False
        changed = True
        print("hostBringUp hibernate exit: inserted")

    if changed and not check_only:
        path.write_text(text)
        print("wrote", path)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("native_ufs_cpp", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    ok = patch(args.native_ufs_cpp, args.check)
    if args.check:
        print("applied" if ok else "NOT applied")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
