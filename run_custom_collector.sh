#!/bin/bash

# ==============================================================================
# Custom Switch Repositories Collector Runner for Linux / Server
# Tracks target authors (NaGaa95, ChanseyIsTheBest, delsonazevedo, boraeskicioglu, PalindromicBreadLoaf)
# ==============================================================================

set -e

# Change to project root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "Running Custom Switch Repositories Collector..."
echo "(NaGaa95, ChanseyIsTheBest, delsonazevedo, boraeskicioglu, PalindromicBreadLoaf)"
echo "=================================================="

# Activate Python virtual environment if present
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Detect Python interpreter
if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
else
    echo "ERROR: Python interpreter (python3/python) not found in PATH."
    exit 1
fi

# Run the collector script
$PYTHON_BIN collect_custom_releases.py
EXIT_CODE=$?

echo "=================================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "Custom Collector completed successfully."
else
    echo "Custom Collector exited with code $EXIT_CODE."
fi
echo "=================================================="

exit $EXIT_CODE
