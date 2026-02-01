#!/usr/bin/env bash
# PreToolUse hook: surface pending mail notifications to the agent.
#
# The SSE watcher (watch_mail.py --sentinel-file) writes a JSON file
# whenever a new message arrives.  This hook reads that file and prints
# a short reminder so the agent sees it before every tool call.
#
# Once the agent calls fetch_inbox (or any MCP mail tool), the sentinel
# is consumed (deleted) to avoid repeat noise.
#
# Usage in .claude/settings.local.json:
#   "PreToolUse": [
#     {
#       "matcher": "",
#       "hooks": [{
#         "type": "command",
#         "command": "/path/to/.claude/hooks/check_notifications.sh"
#       }]
#     }
#   ]
#
# Environment variables:
#   AGENT_MAIL_SENTINEL  - Path to sentinel file
#                          (default: /tmp/mcp-mail-pending-<agent>.json)
#   AGENT_MAIL_AGENT     - Agent name (used for default sentinel path)

set -uo pipefail

AGENT="${AGENT_MAIL_AGENT:-}"
SENTINEL="${AGENT_MAIL_SENTINEL:-/tmp/mcp-mail-pending-${AGENT//[^a-zA-Z0-9]/_}.json}"

# No sentinel file => nothing pending
if [[ ! -f "${SENTINEL}" ]]; then
  exit 0
fi

# Read and validate
CONTENT=$(cat "${SENTINEL}" 2>/dev/null || echo "")
if [[ -z "${CONTENT}" ]]; then
  rm -f "${SENTINEL}" 2>/dev/null
  exit 0
fi

# Check age — ignore stale sentinels older than 10 minutes
if command -v stat >/dev/null 2>&1; then
  if [[ "$(uname)" == "Darwin" ]]; then
    FILE_TS=$(stat -f %m "${SENTINEL}" 2>/dev/null || echo 0)
  else
    FILE_TS=$(stat -c %Y "${SENTINEL}" 2>/dev/null || echo 0)
  fi
  NOW=$(date +%s)
  AGE=$(( NOW - FILE_TS ))
  if [[ ${AGE} -gt 600 ]]; then
    rm -f "${SENTINEL}" 2>/dev/null
    exit 0
  fi
fi

# Extract fields from the JSON sentinel
MSG_ID=$(echo "${CONTENT}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id','?'))" 2>/dev/null || echo "?")
FROM=$(echo "${CONTENT}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('from','unknown'))" 2>/dev/null || echo "unknown")
SUBJECT=$(echo "${CONTENT}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('subject','(no subject)'))" 2>/dev/null || echo "(no subject)")
IMPORTANCE=$(echo "${CONTENT}" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('importance','normal'))" 2>/dev/null || echo "normal")

# Print the notification — this output is injected into the agent's context
echo ""
if [[ "${IMPORTANCE}" == "high" || "${IMPORTANCE}" == "urgent" ]]; then
  echo "🔴 URGENT MAIL — check inbox immediately with fetch_inbox"
else
  echo "📬 NEW MAIL — you have an unread message, check inbox with fetch_inbox"
fi
echo "   From: ${FROM} | Subject: ${SUBJECT} (id=${MSG_ID})"
echo ""

# Consume the sentinel so we don't repeat
rm -f "${SENTINEL}" 2>/dev/null

exit 0
