#!/usr/bin/env python3
"""
Agent Mail HTTP Bridge
A simple HTTP server that bridges requests from Claude's bash to the MCP agent-mail server
Run this in WSL: python3 ~/projects/mcp_agent_mail/http_bridge.py
"""

import json
import subprocess

from flask import Flask, jsonify, request

app = Flask(__name__)

# Configuration
MCP_URL = "http://127.0.0.1:8765/mcp/"
BEARER_TOKEN = "6c4e17ca58da12b39dff5eeed8a0bbe7b1a2886e1eeafbc5df833b5aac0f331e"
PROJECT_KEY = "/home/robert/projects/mcp_agent_mail"

def call_mcp(method: str, params: dict) -> dict:
    """Make JSON-RPC call to MCP server"""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params
    }

    cmd = [
        "curl", "-s", "-X", "POST", MCP_URL,
        "-H", "Content-Type: application/json",
        "-H", f"Authorization: Bearer {BEARER_TOKEN}",
        "-d", json.dumps(payload)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"error": f"curl failed: {result.stderr}"}
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e)}

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "service": "agent-mail-bridge"})

@app.route('/ensure_project', methods=['POST'])
def ensure_project():
    """Ensure project exists"""
    response = call_mcp("tools/call", {
        "name": "ensure_project",
        "arguments": {"human_key": PROJECT_KEY}
    })
    return jsonify(response)

@app.route('/register', methods=['POST'])
def register():
    """Register as an agent"""
    data = request.get_json() or {}

    args = {
        "project_key": PROJECT_KEY,
        "program": data.get('program', 'claude-desktop'),
        "model": data.get('model', 'claude-sonnet-4'),
        "task_description": data.get('task_description', 'AI Assistant')
    }

    if data.get('agent_name'):
        args['agent_name'] = data['agent_name']

    response = call_mcp("tools/call", {
        "name": "register_agent",
        "arguments": args
    })
    return jsonify(response)

@app.route('/discover', methods=['GET'])
def discover():
    """Discover agents"""
    resource_uri = "resource://agents/" + PROJECT_KEY.replace("/", "-").lstrip("-")
    response = call_mcp("resources/read", {"uri": resource_uri})
    return jsonify(response)

@app.route('/send', methods=['POST'])
def send_message():
    """Send a message"""
    data = request.get_json()

    response = call_mcp("tools/call", {
        "name": "send_message",
        "arguments": {
            "project_key": PROJECT_KEY,
            "sender_name": data['sender_name'],
            "to": data['to'],
            "subject": data['subject'],
            "body_md": data['body']
        }
    })
    return jsonify(response)

@app.route('/check', methods=['POST'])
def check_messages():
    """Check messages"""
    data = request.get_json()

    response = call_mcp("tools/call", {
        "name": "check_messages",
        "arguments": {
            "project_key": PROJECT_KEY,
            "agent_name": data['agent_name']
        }
    })
    return jsonify(response)

if __name__ == '__main__':
    print("=" * 60)
    print("Agent Mail HTTP Bridge")
    print("=" * 60)
    print(f"MCP Server: {MCP_URL}")
    print(f"Project: {PROJECT_KEY}")
    print("Starting server on http://localhost:5555")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5555, debug=False)
