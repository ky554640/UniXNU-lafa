#!/usr/bin/env python3
"""Shrink the EDK2 exception dump so the boot log survives on the panel.

The AArch64 handler prints x0-x30, all 32 vector registers and a 16 line stack
window. On this board that is about a full screen, so it scrolls every earlier
console line away, and the console is the only channel a bring-up run can be
photographed from. Dropping the vector registers (irrelevant to a data abort)
and narrowing the stack window leaves roughly 28 lines of log visible above the
dump.

Idempotent: running it twice changes nothing.

    python3 wsl_install/patch-exception-dump.py [--check] <path to CpuExceptionHandlerLib.c>
"""
import argparse
import re
import sys
from pathlib import Path

# "  V0 0x%016lx ..." through " V31 0x%016lx ..." - the vector register block.
VECTOR = re.compile(r'DEBUG \(\(DEBUG_ERROR, "\\n?\s*V\d+ 0x')
OLD_WINDOW = 'for (Offset = -256; Offset < 256; Offset += 32)'
NEW_WINDOW = 'for (Offset = -64; Offset < 128; Offset += 32)'


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('source', type=Path)
    parser.add_argument('--check', action='store_true', help='report whether the patch is applied')
    args = parser.parse_args()

    text = args.source.read_text()
    patched = NEW_WINDOW in text and not VECTOR.search(text)

    if args.check:
        print('applied' if patched else 'not applied')
        return 0 if patched else 1

    if patched:
        print('exception dump already patched')
        return 0

    kept = [line for line in text.splitlines(keepends=True) if not VECTOR.search(line)]
    dropped = len(text.splitlines()) - len(kept)
    text = ''.join(kept)

    if OLD_WINDOW in text:
        text = text.replace(OLD_WINDOW, NEW_WINDOW)
    elif NEW_WINDOW not in text:
        raise SystemExit('stack dump loop not found: the source moved, update this script')

    args.source.write_text(text)
    print(f'exception dump patched: {dropped} vector lines dropped, stack window narrowed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
