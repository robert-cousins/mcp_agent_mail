# MCP Agent Mail Setup and Usage Instructions



## Curl Commands Used for Registration and Messaging

### 1. List Available Tools
```bash
curl -s -X POST "http://127.0.0.1:8765/mcp/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### 2. Ensure Project Exists
```bash
curl -s -X POST "http://127.0.0.1:8765/mcp/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"ensure_project","arguments":{"human_key":"/home/robert/projects/mcp_agent_mail"}}}'
```

### 3. Register Agent
```bash
curl -s -X POST "http://127.0.0.1:8765/mcp/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"register_agent","arguments":{"project_key":"/home/robert/projects/mcp_agent_mail","program":"amp","model":"claude-sonnet-4","task_description":"General development tasks and collaboration"}}}'
```

### 4. Discover Available Agents
```bash
curl -s -X POST "http://127.0.0.1:8765/mcp/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d '{"jsonrpc":"2.0","id":3,"method":"resources/read","params":{"uri":"resource://agents/home-robert-projects-mcp-agent-mail"}}'
```

### 5. Send Message to All Other Agents
```bash
curl -s -X POST "http://127.0.0.1:8765/mcp/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HTTP_BEARER_TOKEN" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"send_message","arguments":{"project_key":"/home/robert/projects/mcp_agent_mail","sender_name":"RoseWaterfall","to":["HumanOverseer","SapphirePrairie","RainyValley","LilacForge","BlackMill","HazyDeer","CoralLantern","OliveMarsh","PearlTower","LilacDog","SapphireGorge","MagentaEagle","SapphireWolf","GentleFox","OliveFox"],"subject":"Introduction from RoseWaterfall","body_md":"Hello everyone, I am RoseWaterfall, a new agent joining the project for general development tasks and collaboration."}}}'
```

## Agent Operational Guidelines

### Mail Checking Protocol
- **Check mail every 20 seconds when idle**: Agents should poll their inbox regularly to stay responsive to coordination requests.
- **Immediate acknowledgment**: Upon receiving any message, send an acknowledgment immediately to confirm receipt.
- **Treat messages as user prompts**: Process incoming messages with the same priority and care as direct user instructions.
- **Action and response**: Take appropriate action based on message content and respond promptly.
- **Task completion summary**: At the end of each task initiated via mail, send a comprehensive summary back to the message originator.

### Communication Best Practices
- Use clear, descriptive subject lines
- Include relevant context and timestamps
- Maintain thread continuity for related discussions
- Respect message importance levels (high/urgent messages get priority)
- Use acknowledgments for critical communications

### Error Handling
- If mail server is unreachable, log the issue and retry connection
- Maintain local state of pending communications
- Notify human overseer of persistent communication failures

## Analysis of register_and_send_message.py

### Completeness Assessment

**Strengths:**
- ✅ Complete MCP server integration using JSON-RPC over HTTP
- ✅ Proper error handling with try/catch blocks
- ✅ Agent registration with configurable parameters
- ✅ Dynamic agent discovery via resources API
- ✅ Self-filtering to avoid sending messages to self
- ✅ Structured logging and status reporting
- ✅ Uses subprocess for reliable curl execution

**Areas for Improvement:**
- ⚠️ Hard-coded agent name "ClineAgent" instead of allowing auto-generation
- ⚠️ Typo in message body template: `{ClineAgent}` should be `{agent_name}`
- ⚠️ Limited error recovery (script exits on first failure)
- ⚠️ No retry logic for transient network issues
- ⚠️ Missing validation of server responses
- ⚠️ No configuration file support for server URL/token

**Overall Assessment:** The script is functionally complete for basic registration and messaging, but could benefit from enhanced error handling, configuration flexibility, and input validation for production use.