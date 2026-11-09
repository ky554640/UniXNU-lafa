#!/usr/bin/env python3
"""Add UFS power-on support to NativeUfs.cpp.

The stock ABL powers the UFS controller down (GDSCR PWR_ON=0, HCE=0) and
NativeUfs has no power-on code, so every read-data path (adopt/hostBringUp/root)
fails at "controller not ready for takeover". sheng gets this from the private
libShengPlatformPower.a; lafa must do it itself.

This patch adds to drivers/NativeUfs/NativeUfs.cpp:

1. powerOnUfsController(bool*): the minimal power-on sequence (GDSC
   collapse-clear + retain-ff, AXI/AHB clock enables, HCE=1 + poll) that returns
   whether the controller came up, without panicking. QMP PHY calibration is
   NOT done (its registers are retained across power collapse, confirmed on
   hardware: hcs=0x100f after power-on).

2. powerOnUfs(): a panic-reporting wrapper (probe==2 diagnostic) that runs the
   sequence and reports each register transition.

3. hostBringUp() calls powerOnUfsController() first so the root path
   (native-ufs-root=1) can power the controller before takeover.

4. A probe == 15 branch (kept for reference) and a probe == 2 hook that runs
   powerOnUfs() before inspect().

Idempotent; use --check to verify.
"""
import argparse
import sys
from pathlib import Path

# The power-on core + the panic-reporting wrapper, inserted after inspect().
POWER_ON_FN = r'''
// Power the UFS controller back up. The stock ABL leaves the PHY GDSC collapsed
// (PWR_ON=0) and HCE=0, and NativeUfs otherwise never writes GCC/HC state, so
// every read-data path fails before it starts. sheng has a private PMGR for
// this; lafa does the minimal sequence here. QMP PHY calibration is not done:
// the PHY registers are retained across power collapse (confirmed on hardware:
// hcs=0x100f after power-on). GDSCR bits: 31 PWR_ON, 16 POWER_UP_COMPLETE,
// 13 RETAIN_PERIPH, 11 RETAIN_FF_ENABLE, 0 SW_COLLAPSE. Clock branches: bit31
// CLK_OFF, bit0 EN.
static bool powerOnUfsController (bool *poweredOut)
{
  OSSharedPtr<IOMemoryMap> gccMap;
  uintptr_t gcc = mapPhys (GCC_BASE + 0x77000, 0x1000, gccMap);
  if (!gcc) {
    return false;
  }
  // Deassert SW_COLLAPSE (bit0) and enable RETAIN_FF (bit11): the Linux
  // gdsc_enable() sequence for a POLL_CFG_GDSCR | RETAIN_FF_ENABLE GDSC.
  uint32_t gdsc = read32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000);
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
  bool powered = (read32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000) & 0x80000000U) != 0;
  if (poweredOut) {
    *poweredOut = powered;
  }
  if (!powered) {
    return false;
  }

  // Enable the host controller (HCE, HC offset 0x34 bit0) and wait for the
  // controller to finish initializing.
  OSSharedPtr<IOMemoryMap> hcMap;
  uintptr_t hc = mapPhys (UFS_HC_BASE, UFS_HC_SIZE, hcMap);
  if (!hc) {
    return false;
  }
  write32 (hc, 0x34, 0x1U);            // HCE = 1
  __asm__ volatile ("dsb sy" ::: "memory");
  unsigned hceLoops = 100000;
  while (((read32 (hc, 0x34) & 1U) == 0) && hceLoops--) {
    IODelay (1);
  }
  return (read32 (hc, 0x34) & 1U) != 0;
}

// Diagnostic (probe==2 / probe==15): power the controller on and report each
// register transition on the panel.
static void powerOnUfs (void)
{
  OSSharedPtr<IOMemoryMap> gccMap;
  uintptr_t gcc = mapPhys (GCC_BASE + 0x77000, 0x1000, gccMap);
  uint32_t gdscBefore = gcc ? read32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000) : 0;
  uint32_t axiBefore = gcc ? read32 (gcc, GCC_UFS_PHY_AXI_ENABLE - 0x77000) : 0;
  uint32_t ahbBefore = gcc ? read32 (gcc, GCC_UFS_PHY_AHB_ENABLE - 0x77000) : 0;
  bool powered = false;
  bool ok = powerOnUfsController (&powered);
  uint32_t gdscAfter = gcc ? read32 (gcc, GCC_UFS_PHY_GDSCR - 0x77000) : 0;
  uint32_t axiAfter = gcc ? read32 (gcc, GCC_UFS_PHY_AXI_ENABLE - 0x77000) : 0;
  uint32_t ahbAfter = gcc ? read32 (gcc, GCC_UFS_PHY_AHB_ENABLE - 0x77000) : 0;
  uint32_t hceAfter = 0, hcsAfter = 0;
  if (ok) {
    OSSharedPtr<IOMemoryMap> hcMap;
    uintptr_t hc = mapPhys (UFS_HC_BASE, UFS_HC_SIZE, hcMap);
    if (hc) {
      hceAfter = read32 (hc, 0x34);
      hcsAfter = read32 (hc, 0x30);
    }
  }
  panic ("NATIVE_UFS power-on (ok=%u)\n"
         "gdsc=%08x->%08x (powered=%u)\n"
         "axi=%08x->%08x ahb=%08x->%08x\n"
         "hce=%08x hcs=%08x\n",
         ok, gdscBefore, gdscAfter, powered,
         axiBefore, axiAfter, ahbBefore, ahbAfter,
         hceAfter, hcsAfter);
}

'''

# The probe == 15 branch, inserted before the probe == 13 branch.
PROBE_15_FN = r'''
  if (probe == 15) {
    // Power the controller back up and report each register transition.
    powerOnUfs ();
  }
'''

# Also run powerOnUfs from the probe == 2 path (confirmed to fire on hardware).
PROBE_2_CALL = "powerOnUfs ();\n"
ANCHOR_PROBE_2_INSPECT = "  if (probe == 2) {\n    inspect ();\n  }"

# hostBringUp(): power on before mapping/takeover.
ANCHOR_HOSTBRINGUP = "  if (gHost.ready) {\n    return true;\n  }"
HOSTBRINGUP_NEW = "  if (gHost.ready) {\n    return true;\n  }\n  if (!powerOnUfsController (nullptr)) {\n    *why = \"power on\";\n    return false;\n  }"

ANCHOR_FN_END = "}\n\n// Adopt the controller the firmware left running (native-ufs-probe=3) and issue"
ANCHOR_PROBE_13 = "  if (probe == 13) {"


def patch(path: Path, check_only: bool) -> bool:
    text = path.read_text()
    changed = False

    if POWER_ON_FN.strip() not in text:
        if check_only:
            print("powerOnUfs(): not applied")
            return False
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

    if "powerOnUfsController (nullptr)" not in text:
        if check_only:
            print("hostBringUp power-on: not applied")
            return False
        if ANCHOR_HOSTBRINGUP not in text:
            print("anchor (hostBringUp gHost.ready) not found")
            return False
        text = text.replace(ANCHOR_HOSTBRINGUP, HOSTBRINGUP_NEW, 1)
        changed = True
        print("hostBringUp power-on: inserted")

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
