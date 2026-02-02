#!/bin/bash
# Run MCP Agent Mail watcher in a tmux session with auto-restart
#
# Usage: ./run-watcher-tmux.sh <agent_name> [project_slug] [server_url]
#
# Examples:
#   ./run-watcher-tmux.sh OrangeWolf
#   ./run-watcher-tmux.sh OrangeWolf data-projects-mcp-agent-mail http://127.0.0.1:8765

set -e

AGENT_NAME="${1:?Usage: $0 <agent_name> [project_slug] [server_url]}"
PROJECT_SLUG="${2:-data-projects-mcp-agent-mail}"
SERVER_URL="${3:-http://127.0.0.1:8765}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
SESSION_NAME="watcher-${AGENT_NAME}"

# Check if tmux session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session '$SESSION_NAME' already exists. Attaching..."
    tmux attach-session -t "$SESSION_NAME"
    exit 0
fi

# Create new tmux session with watcher loop
tmux new-session -d -s "$SESSION_NAME" bash -c "
    cd '$REPO_DIR'
    source .venv/bin/activate
    
    while true; do
        echo '=========================================='
        echo \"[\$(date)] Starting watcher for $AGENT_NAME\"
        echo '=========================================='
        
        uv run python scripts/watch_mail.py \\
            --method sse \\
            --project '$PROJECT_SLUG' \\
            --agent '$AGENT_NAME' \\
            --url '$SERVER_URL' \\
            --buffer-file PENDING_NOTIFICATIONS.md \\
            --sentinel-file /tmp/mcp-mail-pending-${AGENT_NAME}.json \\
            --dev-notify \\
            --auto-fetch \\
            --show-body
        
        EXIT_CODE=\$?
        echo ''
        echo \"[\$(date)] Watcher exited with code \$EXIT_CODE. Restarting in 5s...\"
        sleep 5
    done
"

echo "Started watcher session '$SESSION_NAME'"
echo ""
echo "Commands:"
echo "  Attach:  tmux attach-session -t $SESSION_NAME"
echo "  Detach:  Ctrl+B, D (while attached)"
echo "  Kill:    tmux kill-session -t $SESSION_NAME"
echo ""
echo "Attaching now..."
tmux attach-session -t "$SESSION_NAME"
