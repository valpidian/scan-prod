from __future__ import annotations

import argparse
import ctypes
import sys


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def is_running(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    args = parser.parse_args()
    sys.stdout.write("1" if is_running(args.pid) else "0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
