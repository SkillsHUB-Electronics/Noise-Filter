"""Entry point of the frozen Windows app (PyInstaller). No arguments opens the UI."""
import sys

from noise_filter.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["ui"]))
