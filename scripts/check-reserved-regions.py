#!/usr/bin/env python3
"""Check a device tree's reserved-memory regions against the UEFI memory map.

The map in Platforms/<vendor>/<board>Pkg/Library/MemoryMapLib is what the
firmware knows: entries typed Reserv are kept away from the allocator, entries
typed Conv/BsData/RtData are handed out as pool. A bootloader carveout that
lands inside an allocatable entry gets written over by UEFI, which shows up
later as an unrelated hang, so that case is a hard failure. A carveout the map
does not mention at all is reported as information only, because the firmware
never sees that address in the first place.

    python3 scripts/check-reserved-regions.py lafa_dtb8.dtb

Exits non-zero when a reserved region overlaps allocatable firmware memory.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

DEVICE = Path(__file__).resolve().parents[1]
DEFAULT_MAP = DEVICE.parent / 'Mu-Silicium/Platforms/Realme/lafaPkg/Library/MemoryMapLib/MemoryMapLib.c'

# {"Name", 0xADDR, 0xLEN, HobOption, ResourceAttribute, ArmAttributes, ResourceType, MemoryType}
ROW = re.compile(r'\{"([^"]+)",\s*(0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+),\s*'
                 r'\w+,\s*\w+,\s*\w+,\s*(\w+),\s*(\w+)\}')
ALLOCATABLE = {'Conv', 'BsData', 'RtData', 'BsCode'}


def dt_regions(dtb):
    """Yield (name, start, end) for every /reserved-memory node that has a reg."""
    names = subprocess.check_output(['fdtget', '-l', str(dtb), '/reserved-memory'], text=True).split()
    for name in names:
        try:
            value = subprocess.check_output(
                ['fdtget', '-t', 'x', str(dtb), '/reserved-memory/' + name, 'reg'],
                text=True, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            continue  # size + alloc-ranges: the bootloader picks the address at runtime
        cells = [int(cell, 16) for cell in value.split()]
        if len(cells) % 4:
            continue
        for a, b, c, d in zip(cells[::4], cells[1::4], cells[2::4], cells[3::4]):
            start, size = a << 32 | b, c << 32 | d
            if size:
                yield name, start, start + size


def map_regions(source):
    regions = [(name, int(base, 16), int(base, 16) + int(size, 16), kind, mem)
               for name, base, size, kind, mem in ROW.findall(source)]
    if not regions:
        raise SystemExit('no memory map entries parsed: is this MemoryMapLib.c?')
    return regions


def merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('dtb', type=Path, help='device tree to check (the bootloader-selected one)')
    parser.add_argument('--map', type=Path, default=DEFAULT_MAP, help='MemoryMapLib.c to read')
    args = parser.parse_args()

    regions = map_regions(args.map.read_text())
    reserved = merge([(s, e) for _, s, e, _, mem in regions if mem not in ALLOCATABLE])
    allocatable = merge([(s, e) for _, s, e, _, mem in regions if mem in ALLOCATABLE])
    known = merge([(s, e) for _, s, e, _, _ in regions])

    failures = uncovered = 0
    for name, start, end in sorted(dt_regions(args.dtb), key=lambda r: r[1]):
        if any(s <= start and end <= e for s, e in reserved):
            continue
        hits = [(s, e) for s, e in allocatable if start < e and s < end]
        if hits:
            print(f'FAIL {name} [{start:#x},{end:#x}) lands in allocatable firmware memory '
                  + ', '.join(f'[{s:#x},{e:#x})' for s, e in hits))
            failures += 1
        elif not any(start < e and s < end for s, e in known):
            print(f'info {name} [{start:#x},{end:#x}) is not in the firmware map at all')
            uncovered += 1
    print(f'{len(regions)} map entries; {failures} regions overlap allocatable memory, '
          f'{uncovered} unknown to the map')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
