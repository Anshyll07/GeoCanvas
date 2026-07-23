"""
Root CLI entry point for map generation. Forwards directly to cli/generate.py.
"""

import sys
from pathlib import Path

# Add cli directory to sys.path
CLI_DIR = Path(__file__).resolve().parent / "cli"
sys.path.insert(0, str(CLI_DIR))

from generate import main

if __name__ == "__main__":
    main()
