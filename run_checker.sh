#!/bin/bash

# Universal checker script for RuTracker bot
# Usage:
#   ./run_checker.sh           - Run main RuTracker checker (default)
#   ./run_checker.sh rt        - Run RuTracker checker
#   ./run_checker.sh hb        - Run Homebrew updates checker
#   ./run_checker.sh digest    - Send daily digest
#   ./run_checker.sh hb-digest - Send homebrew digest

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# GitHub token should be set in environment or loaded from local config
# Example: export GITHUB_TOKEN="your_token_here"
if [ -z "$GITHUB_TOKEN" ]; then
    echo "Warning: GITHUB_TOKEN not set. Homebrew checker may hit rate limits."
fi

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Parse command
COMMAND="${1:-rt}"

case "$COMMAND" in
    rt|rutracker)
        echo "=== Running RuTracker checker ==="
        python main.py
        ;;

    hb|homebrew)
        echo "=== Running Homebrew updates checker ==="
        python collect_homebrew_updates.py
        ;;

    digest|daily-digest)
        echo "=== Sending daily digest ==="
        python send_daily_digest.py
        ;;

    hb-digest|homebrew-digest)
        echo "=== Sending homebrew digest ==="
        python send_homebrew_digest.py
        ;;

    all)
        echo "=== Running all checkers ==="
        echo ""
        echo "--- RuTracker checker ---"
        python main.py
        echo ""
        echo "--- Homebrew checker ---"
        python collect_homebrew_updates.py
        ;;

    help|--help|-h)
        echo "Usage: $0 [COMMAND]"
        echo ""
        echo "Commands:"
        echo "  rt, rutracker       Run RuTracker checker (default)"
        echo "  hb, homebrew        Run Homebrew updates checker"
        echo "  digest              Send daily digest"
        echo "  hb-digest           Send homebrew digest"
        echo "  all                 Run all checkers"
        echo "  help                Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                  # Run RuTracker checker"
        echo "  $0 hb               # Check homebrew updates"
        echo "  $0 hb-digest        # Send homebrew digest"
        ;;

    *)
        echo "Error: Unknown command '$COMMAND'"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac

exit 0
