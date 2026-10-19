#!/bin/bash
# Double-click to open the SMT Recomp launcher in your browser.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is missing. Install it with:  xcode-select --install"
    read -r -p "Press Return to close."
    exit 1
fi
exec python3 smt_launcher.py "$@"
