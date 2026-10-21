#!/usr/bin/env python3
"""rfp-analyzer CLI entry point. Run `python rfp.py --help`."""
import sys
from pathlib import Path

if sys.version_info < (3, 9):
    sys.exit("rfp-analyzer requires Python 3.9 or newer.")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rfp_lib.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
