#!/bin/bash
# Double-click launcher for macOS. First run may need: xcode-select --install (for python3), and
# macOS may ask to allow incoming connections so your phone can reach the game.
cd "$(dirname "$0")"
command -v python3 >/dev/null 2>&1 || { echo "python3 not found. Install the Xcode command line tools (xcode-select --install) or Python from python.org, then run this again."; read -n 1; exit 1; }
python3 backend/main.py "$@"
