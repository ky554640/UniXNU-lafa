#!/usr/bin/env python3
"""Refuse a firmware volume that could disturb persistent state.

Running this platform's UEFI on the phone twice left it a black brick that only
a service-centre reflash recovered. Nothing here writes partitions, so the harm
has to come from a driver that programs something persistent behind our back:
the UFS controller that holds XBL, the SD card controller, or a TrustZone call.

This audit is the gate in front of every hardware run.

    python3 tools/audit-fd.py            # source lists + built volume
    python3 tools/audit-fd.py --lists    # only the INF lists, no build needed

Exit status is non-zero when a forbidden module is present.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'Mu-Silicium/Platforms/Realme/lafaPkg'
LISTS = [PKG / 'Include/DXE.inc', PKG / 'Include/APRIORI.inc']
# build-uefi.sh exports the uncompressed volume here; the FD itself is LZMA
# compressed, so the module names inside it are not greppable.
FVMAIN = ROOT / 'out_lafa/FVMAIN.Fv'

# Module name fragment -> why it is fatal. These program a controller or region
# that survives a reboot; anything here means the image must not reach the phone.
FORBIDDEN = {
    'UFSDxe': 'programs the UFS controller that holds XBL and the partition table',
    'SdccDxe': 'programs the SD card controller',
    'OplusProject': 'crashes with a null interface call and writes vendor project data',
}
# Present but not fatal. TrustZone and the USB mass-storage class can reach
# persistent state only through a storage driver, which is already gone, and the
# charger/PMIC paths are needed for the panel rails.
WARN = {
    'TzDxe': 'TrustZone calls',
    'ScmDxeCompat': 'SCM calls',
    'ShmBridgeDxe': 'shared memory with TrustZone',
    'UsbMsdDxe': 'USB mass storage class',
    'QcomChargerDxe': 'charger/PMIC registers',
    'ChargerExDxe': 'charger/PMIC registers',
    'PmicDxe': 'PMIC registers',
}

INF = re.compile(r'^\s*INF\s+(\S+)')


def active_modules(path):
    """Yield (name, line number) for INF lines that are not commented out."""
    for number, line in enumerate(path.read_text(errors='replace').splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        match = INF.match(stripped)
        if match:
            yield Path(match.group(1)).stem, number


def audit_lists():
    findings = []
    total = 0
    for path in LISTS:
        if not path.is_file():
            findings.append(('missing', path, 0, 'file not found'))
            continue
        for name, number in active_modules(path):
            total += 1
            for fragment, reason in FORBIDDEN.items():
                if fragment in name:
                    findings.append(('forbidden', path, number, f'{name}: {reason}'))
    return total, findings


def audit_volume():
    if not FVMAIN.is_file():
        return None
    data = FVMAIN.read_bytes()
    found = []
    for fragment, reason in {**FORBIDDEN, **WARN}.items():
        # Match the module as an EFI/DLL image name (its file name is stored in the
        # firmware volume's file list), not as a bare substring: a forbidden name
        # can also survive as a string literal or a path inside an unrelated
        # driver ("Locate OplusProject protocol failed"). Those are harmless.
        names = re.findall(rb'([A-Za-z0-9_]+\.(?:efi|dll|pe32|ui|fv))', data)
        if any(fragment.encode() in name for name in names):
            found.append((fragment, reason))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--lists', action='store_true', help='skip the built volume')
    args = parser.parse_args()

    total, findings = audit_lists()
    forbidden = [f for f in findings if f[0] == 'forbidden']
    missing = [f for f in findings if f[0] == 'missing']
    print(f'INF 列表: {total} 个模块，{len(forbidden)} 个禁止项')
    for _, path, number, detail in forbidden:
        print(f'  FAIL {path.name}:{number}  {detail}')
    for _, path, _, detail in missing:
        print(f'  FAIL {path} {detail}')

    volume_problem = False
    if not args.lists:
        found = audit_volume()
        if found is None:
            print(f'  构建产物不存在，跳过卷检查: {FVMAIN}')
        else:
            bad = [(n, r) for n, r in found if n in FORBIDDEN]
            warn = [(n, r) for n, r in found if n in WARN]
            print(f'固件卷: 禁止项 {len(bad)} 个，提示项 {len(warn)} 个')
            for name, reason in bad:
                print(f'  FAIL 卷内仍含 {name}（{reason}）')
                volume_problem = True
            for name, reason in warn:
                print(f'  note 卷内含 {name}（{reason}）')

    ok = not forbidden and not missing and not volume_problem
    print('结论:', '通过，可以上机' if ok else '不通过，禁止上机')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
