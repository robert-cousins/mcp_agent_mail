#!/bin/bash

# Agent Mail MCP Server Test Script
# This script tests the complete workflow of the agent-mail system

# Configuration
MCP_URL="http://127.0.0.1:8765/mcp/"
HTTP_BEARER_TOKEN="6c4e17ca58da12b39dff5eeed8a0bbe7b1a2886e1eeafbc5df833b5aac0f331e"
PROJECT_KEY="/home/robert/projects/mcp_agent_mail"
AGENT_NAME="ClaudeTestAgent"

echo "=========================================="
echo "Agent Mail MCP Server Test"
echo "=========================================="
echo ""

# Test 1: List Available Tools
echo "Test 1: Listing available tools..."
echo "------------------------------------------"
TOOLS_RESPONSE=$(curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')

echo "$TOOLS_RESPONSE" | jq '.'
echo ""

# Test 2: Ensure Project Exists
echo "Test 2: Ensuring project exists..."
echo "------------------------------------------"
PROJECT_RESPONSE=$(curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"ensure_project\",\"arguments\":{\"human_key\":\"$PROJECT_KEY\"}}}")

echo "$PROJECT_RESPONSE" | jq '.'
echo ""

# Test 3: Register Agent
echo "Test 3: Registering agent '$AGENT_NAME'..."
echo "------------------------------------------"
REGISTER_RESPONSE=$(curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"register_agent\",\"arguments\":{\"project_key\":\"$PROJECT_KEY\",\"program\":\"claude-test\",\"model\":\"claude-sonnet-4\",\"task_description\":\"Testing agent mail functionality\"}}}")

echo "$REGISTER_RESPONSE" | jq '.'

# Extract the agent name from the response
AGENT_NAME_FROM_RESPONSE=$(echo "$REGISTER_RESPONSE" | jq -r '.result.content[0].text' 2>/dev/null | grep -oP 'Agent \K\w+' | head -1)
if [ -n "$AGENT_NAME_FROM_RESPONSE" ]; then
    AGENT_NAME="$AGENT_NAME_FROM_RESPONSE"
    echo "Registered as: $AGENT_NAME"
fi
echo ""

# Test 4: Discover Available Agents
echo "Test 4: Discovering available agents..."
echo "------------------------------------------"
RESOURCE_URI="resource://agents/$(echo $PROJECT_KEY | sed 's/\//-/g' | sed 's/^-//')"
AGENTS_RESPONSE=$(curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"resources/read\",\"params\":{\"uri\":\"$RESOURCE_URI\"}}")

echo "$AGENTS_RESPONSE" | jq '.'
echo ""

# Extract list of other agents (excluding ourselves)
OTHER_AGENTS=$(echo "$AGENTS_RESPONSE" | jq -r '.result.contents[0].text' 2>/dev/null | grep -oP 'name=\K\w+' | grep -v "^$AGENT_NAME$" | jq -R -s -c 'split("\n") | map(select(length > 0))')

echo "Other agents found: $OTHER_AGENTS"
echo ""

# Test 5: Send a Test Message
if [ "$OTHER_AGENTS" != "null" ] && [ "$OTHER_AGENTS" != "[]" ]; then
    echo "Test 5: Sending test message to other agents..."
    echo "------------------------------------------"
    
    MESSAGE_RESPONSE=$(curl -s -X POST "$MCP_URL" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
      -d "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"tools/call\",\"params\":{\"name\":\"send_message\",\"arguments\":{\"project_key\":\"$PROJECT_KEY\",\"sender_name\":\"$AGENT_NAME\",\"to\":$OTHER_AGENTS,\"subject\":\"Test Message from $AGENT_NAME\",\"body_md\":\"Hello! This is a test message to verify the agent mail system is working correctly.\"}}}")
    
    echo "$MESSAGE_RESPONSE" | jq '.'
    echo ""
else
    echo "Test 5: Skipped (no other agents found to message)"
    echo ""
fi

# Test 6: Check for Messages (if inbox checking is available)
echo "Test 6: Checking for messages..."
echo "------------------------------------------"
INBOX_RESPONSE=$(curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":6,\"method\":\"tools/call\",\"params\":{\"name\":\"check_messages\",\"arguments\":{\"project_key\":\"$PROJECT_KEY\",\"agent_name\":\"$AGENT_NAME\"}}}")

echo "$INBOX_RESPONSE" | jq '.'
echo ""

echo "=========================================="
echo "Test Complete!"
echo "=========================================="