#!/usr/bin/env python3
"""Add a UFS power-on probe (native-ufs-probe=15) to NativeUfs.cpp.

The stock ABL powers the UFS controller down (GDSCR PWR_ON=0, HCE=0) and
NativeUfs has no power-on code, so every read-data path (adopt/hostBringUp/root)
fails at "controller not ready for takeover". sheng gets this from the private
libShengPlatformPower.a; lafa must do it itself.

This patch adds two things to drivers/NativeUfs/NativeUfs.cpp:

1. A powerOnUfs() helper that powers the UFS PHY GDSC and the AXI/AHB clock
   branches, then enables HCE and waits for UTMRLRDY. The register offsets come
   from GccUfs.h and the Linux gcc-sm8550.c / gdsc.c (v6.1) definitions. The
   sequence is deliberately minimal: GDSC collapse-clear + retain-ff, clock
   branch enables, HCE=1 + poll. QMP PHY calibration is NOT done here (its
   registers are reported to be retained across power collapse).

2. A probe == 15 branch that runs powerOnUfs() and reports the register state at
   each step via panic(), so the bring-up state can be read off the panel.

Idempotent: running twice leaves the file unchanged. Use --check to verify the
patch is present.
"""
import argparse
import sys
from pathlib import Path

# GDSCR bit definitions (Linux gdsc.c v6.1, matching SM8550/SM8850).
POWER_ON_FN = r'''
// Power the UFS controller back up. The stock ABL leaves the PHY GDSC collapsed
// (PWR_ON=0) and HCE=0, and NativeUfs otherwise never writes GCC/HC state, so
// every read-data path fails before it starts. sheng has a private PMGR for
// this; lafa does the minimal sequence here. QMP PHY calibration is not done:
// the PHY registers are reported to be retained across power collapse, so the
// firmware's calibration should still hold once the domain and clocks are back.
// GDSCR bits: 31 PWR_ON, 16 POWER_UP_COMPLETE, 14 RETAIN_MEM, 13 RETAIN_PERIPH,
// 11 RETAIN_FF_ENABLE, 0 SW_COLLAPSE. Clock branches: bit31 CLK_OFF, bit0 EN.
static void powerOnUfs (void)
{
  OSSharedPtr<IOMemoryMap> gccMap;
  uintptr_t gcc = mapPhys (GCC_BASE + 0x77000, 0x1000, gccMap);
  if (!gcc) {
    panic ("NATIVE_UFS power-on: GCC map failed");
  }
  uint32_t gdscBefore = read32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000);
  uint32_t axiBefore = read32 (gcc, GCC_UFS_PHY_AXI_ENABLE - 0x77000);
  uint32_t ahbBefore = read32 (gcc, GCC_UFS_PHY_AHB_ENABLE - 0x77000);

  // Deassert SW_COLLAPSE (bit0) and enable RETAIN_FF (bit11): this is the
  // Linux gdsc_enable() sequence for a POLL_CFG_GDSCR | RETAIN_FF_ENABLE GDSC.
  uint32_t gdsc = gdscBefore;
  gdsc &= ~0x1U;          // SW_COLLAPSE = 0
  gdsc |= 0x800U;         // RETAIN_FF_ENABLE = 1
  write32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000, gdsc);
  IODelay (1);

  // Enable the AXI and AHB clock branches (clear CLK_OFF bit31, set EN bit0).
  write32 (gcc, GCC_UFS_PHY_AXI_ENABLE - 0x77000, 0x1U);
  write32 (gcc, GCC_UFS_PHY_AHB_ENABLE - 0x77000, 0x1U);
  __asm__ volatile ("dsb sy" ::: "memory");

  // Poll PWR_ON (bit31).
  unsigned powerLoops = 10000;
  while (((read32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000) & 0x80000000U) == 0) && powerLoops--) {
    IODelay (1);
  }
  uint32_t gdscAfter = read32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000);
  uint32_t axiAfter = read32 (gcc, GCC_UFS_PHY_AXI_ENABLE - 0x77000);
  uint32_t ahbAfter = read32 (gcc, GCC_UFS_PHY_AHB_ENABLE - 0x77000);
  bool powered = (gdscAfter & 0x80000000U) != 0;

  // Enable the host controller (HCE, HC offset 0x34 bit0) and wait for the
  // controller to finish initializing (UTMRLRDY/UTMRLS in HCS offset 0x30).
  uint32_t hceBefore = 0, hceAfter = 0, hcsAfter = 0;
  if (powered) {
    OSSharedPtr<IOMemoryMap> hcMap;
    uintptr_t hc = mapPhys (UFS_HC_BASE, UFS_HC_SIZE, hcMap);
    if (hc) {
      hceBefore = read32 (hc, 0x34);
      write32 (hc, 0x34, 0x1U);            // HCE = 1
      __asm__ volatile ("dsb sy" ::: "memory");
      unsigned hceLoops = 100000;
      hceAfter = read32 (hc, 0x34);
      while (((hceAfter & 1U) == 0) && hceLoops--) {
        IODelay (1);
        hceAfter = read32 (hc, 0x34);
      }
      hcsAfter = read32 (hc, 0x30);
    }
  }

  panic ("NATIVE_UFS power-on\n"
         "gdsc=%08x->%08x (powered=%u)\n"
         "axi=%08x->%08x ahb=%08x->%08x\n"
         "hce=%08x->%08x hcs=%08x\n",
         gdscBefore, gdscAfter, powered,
         axiBefore, axiAfter, ahbBefore, ahbAfter,
         hceBefore, hceAfter, hcsAfter);
}

'''

# The probe == 15 branch, inserted before the probe == 13 branch.
PROBE_15_FN = r'''
  if (probe == 15) {
    // Power the controller back up and report each register transition, so the
    // bring-up state can be read off the panel. Read-only with respect to the
    // storage: only the GCC clock domain and the HC enable bit are written.
    powerOnUfs ();
  }
'''

# Also run powerOnUfs from the probe == 2 path, which is the one confirmed to
# fire on hardware (probe == 15 did not). The call is placed before inspect() so
# the power-on result, not the pre-power state, is what gets reported.
PROBE_2_CALL = "powerOnUfs ();\n"
ANCHOR_PROBE_2_INSPECT = "  if (probe == 2) {\n    inspect ();\n  }"

ANCHOR_FN_END = "}\n\n// Adopt the controller the firmware left running (native-ufs-probe=3) and issue"
ANCHOR_PROBE_13 = "  if (probe == 13) {"


def patch(path: Path, check_only: bool) -> bool:
    text = path.read_text()
    changed = False

    if POWER_ON_FN.strip() not in text:
        if check_only:
            print("powerOnUfs(): not applied")
            return False
        # Insert the function right after inspect()'s closing brace, before the
        # "Adopt the controller" comment.
        if ANCHOR_FN_END not in text:
            print("anchor (inspect end / adopt comment) not found")
            return False
        text = text.replace(ANCHOR_FN_END, "}\n\n" + POWER_ON_FN + "// Adopt the controller the firmware left running (native-ufs-probe=3) and issue", 1)
        changed = True
        print("powerOnUfs(): inserted")

    if PROBE_15_FN.strip() not in text:
        if check_only:
            print("probe == 15: not applied")
            return False
        if ANCHOR_PROBE_13 not in text:
            print("anchor (probe == 13) not found")
            return False
        text = text.replace(ANCHOR_PROBE_13, PROBE_15_FN + "\n" + ANCHOR_PROBE_13, 1)
        changed = True
        print("probe == 15: inserted")

    # Run powerOnUfs from probe == 2 too, before inspect(). The anchor is the
    # existing probe == 2 block; replace it with a version that powers on first.
    PROBE_2_NEW = "  if (probe == 2) {\n    powerOnUfs ();\n    inspect ();\n  }"
    if "    powerOnUfs ();\n    inspect ();" not in text:
        if check_only:
            print("probe == 2 powerOnUfs: not applied")
            return False
        if ANCHOR_PROBE_2_INSPECT not in text:
            print("anchor (probe == 2 inspect) not found")
            return False
        text = text.replace(ANCHOR_PROBE_2_INSPECT, PROBE_2_NEW, 1)
        changed = True
        print("probe == 2 powerOnUfs: inserted")

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
