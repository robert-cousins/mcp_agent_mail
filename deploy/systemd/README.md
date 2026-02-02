# Systemd Service for MCP Agent Mail Watcher

This directory contains a systemd user service template for running per-agent watchers with automatic restart.

## Quick Start

```bash
# 1. Copy service file to user systemd directory
mkdir -p ~/.config/systemd/user
cp mcp-agent-mail-watcher@.service ~/.config/systemd/user/

# 2. (Optional) Create config file for overrides
mkdir -p ~/.config/mcp-agent-mail
cat > ~/.config/mcp-agent-mail/watcher.env << 'EOF'
PROJECT_SLUG=data-projects-mcp-agent-mail
SERVER_URL=http://127.0.0.1:8765
# HTTP_BEARER_TOKEN=your-token-here
EOF

# 3. Reload systemd
systemctl --user daemon-reload

# 4. Start watcher for your agent
systemctl --user start mcp-agent-mail-watcher@OrangeWolf

# 5. Enable auto-start on login
systemctl --user enable mcp-agent-mail-watcher@OrangeWolf
```

## Commands

```bash
# Check status
systemctl --user status mcp-agent-mail-watcher@OrangeWolf

# View logs (follow mode)
journalctl --user -u mcp-agent-mail-watcher@OrangeWolf -f

# Restart
systemctl --user restart mcp-agent-mail-watcher@OrangeWolf

# Stop
systemctl --user stop mcp-agent-mail-watcher@OrangeWolf

# Disable auto-start
systemctl --user disable mcp-agent-mail-watcher@OrangeWolf
```

## Multiple Agents

Run watchers for multiple agents simultaneously:

```bash
systemctl --user start mcp-agent-mail-watcher@OrangeWolf
systemctl --user start mcp-agent-mail-watcher@SapphireOtter
systemctl --user start mcp-agent-mail-watcher@CyanHawk
```

## Features

- **Auto-restart**: Restarts on failure with exponential backoff (5s to 5min)
- **Logging**: All output goes to systemd journal
- **Per-agent isolation**: Each agent runs as a separate service instance
- **User-level**: No root required, runs under your user account

## Alternative: tmux Script

For simpler setups without systemd, use the tmux script:

```bash
./run-watcher-tmux.sh OrangeWolf
```
