"""Run the monitor: python -m syncbridge.monitor"""
from __future__ import annotations

import sys


def main(argv=None) -> int:
    from .window import run
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
