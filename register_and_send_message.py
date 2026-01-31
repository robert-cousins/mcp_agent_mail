#!/usr/bin/env python3
"""
Script to register with the MCP Agent Mail server and send an introduction message to all users.
"""

import json
import subprocess
from datetime import datetime

# Server configuration
SERVER_URL = "http://127.0.0.1:8765/mcp/"
BEARER_TOKEN = "HTTP_BEARER_TOKEN"

def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Call an MCP tool via HTTP JSON-RPC using curl."""
    payload = {
        "jsonrpc": "2.0",
        "id": f"cli-{tool_name}-{datetime.now().isoformat()}",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", SERVER_URL,
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: Bearer {BEARER_TOKEN}",
             "-d", json.dumps(payload)],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(result.stdout)
        # Extract structuredContent which contains the actual result
        structured_content = data.get("result", {}).get("structuredContent", {})
        return structured_content
    except Exception as e:
        print(f"Error calling {tool_name}: {e}")
        return {}

def get_all_agents(project_key: str) -> list[str]:
    """Get all registered agents in a project using curl."""
    try:
        resource_payload = {
            "jsonrpc": "2.0",
            "id": "get-agents",
            "method": "resources/read",
            "params": {
                "uri": f"resource://agents/{project_key}"
            }
        }

        result = subprocess.run(
            ["curl", "-s", "-X", "POST", SERVER_URL,
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: Bearer {BEARER_TOKEN}",
             "-d", json.dumps(resource_payload)],
            capture_output=True,
            text=True,
            check=True
        )
        data = json.loads(result.stdout)
        contents = data.get("result", {}).get("contents", [])

        if contents:
            # The agents data is in the text field of the first content
            agents_text = contents[0].get("text", "[]")
            agents_data = json.loads(agents_text)
            result_data = agents_data.get("result", {})
            if "agents" in result_data:
                return [agent["name"] for agent in result_data["agents"]]
        return []
    except Exception as e:
        print(f"Error getting agents: {e}")
        return []

def main():
    print("Starting registration and messaging process...")

    # Step 1: Ensure the project exists
    project_key = "/home/robert/projects/mcp_agent_mail"
    print(f"Ensuring project: {project_key}")

    project_result = call_mcp_tool("ensure_project", {
        "human_key": project_key
    })

    if not project_result:
        print("Failed to ensure project")
        return

    project_slug = project_result.get("slug", "unknown")
    print(f"Project ensured: {project_slug}")

    # Step 2: Register myself as an agent
    agent_name = "ClineAgent"
    print(f"Registering agent: {agent_name}")

    register_result = call_mcp_tool("register_agent", {
        "project_key": project_key,
        "program": "python-script",
        "model": "custom-agent",
        "name": agent_name,
        "task_description": "Register with server and introduce myself to all users"
    })

    if not register_result:
        print("Failed to register agent")
        return

    print(f"Agent registered: {register_result.get('name', 'unknown')}")

    # Step 3: Get all agents in the project
    print("Getting all registered agents...")
    all_agents = get_all_agents(project_key)

    print(f"Debug: All agents found: {all_agents}")

    if not all_agents:
        print("No agents found in the project")
        return

    print(f"Found {len(all_agents)} agents: {', '.join(all_agents)}")

    # Filter out myself to avoid sending to myself
    registered_agent_name = register_result.get('name', agent_name)
    other_agents = [agent for agent in all_agents if agent != registered_agent_name]

    print(f"Debug: Registered agent name: {registered_agent_name}")
    print(f"Debug: Other agents after filtering: {other_agents}")

    if not other_agents:
        print("No other agents to send messages to")
        return

    # Step 4: Send introduction message to all other agents
    subject = "Hello from ClineAgent!"
    body = f"""Hello everyone!

I'm ClineAgent, a new agent that has just registered with the MCP Agent Mail server. I'm here to help with coordination and communication between agents.

I'm excited to work with all of you on this project. Let me know if there's anything I can assist with!

Best regards,
{agent_name}

Current time: {datetime.now().isoformat()}
Project: {project_key}
"""

    print(f"Sending introduction message to {len(other_agents)} agents...")

    send_result = call_mcp_tool("send_message", {
        "project_key": project_key,
        "sender_name": agent_name,
        "to": other_agents,
        "subject": subject,
        "body_md": body,
        "importance": "normal",
        "ack_required": False
    })

    if send_result and "deliveries" in send_result:
        print(f"Message sent successfully to {len(send_result['deliveries'])} recipients!")
        print("Registration and messaging process completed successfully!")
    else:
        print("Failed to send message")

if __name__ == "__main__":
    main()
