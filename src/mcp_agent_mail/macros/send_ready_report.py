from typing import Any, Optional, Protocol
from mcp_agent_mail.macros.ci_gate import ci_gate

class AMClientProtocol(Protocol):
    def send_message(self, project_key: str, sender_name: str, to: list[str], subject: str, body_md: str) -> dict[str, Any]: ...

class RealAMClient:
    """Real implementation using MCP Agent Mail tools via curl."""
    def send_message(self, project_key: str, sender_name: str, to: list[str], subject: str, body_md: str) -> dict[str, Any]:
        import os
        import json
        import subprocess
        
        token = os.environ.get("HTTP_BEARER_TOKEN", "")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "send_message",
                "arguments": {
                    "project_key": project_key,
                    "sender_name": sender_name,
                    "to": to,
                    "subject": subject,
                    "body_md": body_md
                }
            }
        }
        
        cmd = [
            "curl", "-s", "-X", "POST", "http://127.0.0.1:8765/mcp/",
            "-H", "Content-Type: application/json",
            "-H", f"Authorization: Bearer {token}",
            "-d", json.dumps(payload)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

def send_ready_report(
    project_key: str,
    sender: str,
    recipients: list[str],
    owner: str,
    repo: str,
    pr_number: int,
    local_commands: list[str],
    notes: str = "",
    am_client: Optional[AMClientProtocol] = None
) -> dict[str, Any]:
    """
    Enforce CI gate before sending a 'ready for merge' report.
    """
    if am_client is None:
        am_client = RealAMClient()

    # 1. Check CI Gate
    gate_result = ci_gate(owner=owner, repo=repo, pr_number=pr_number)
    
    if not gate_result["ok"]:
        failed_names = ", ".join([f["name"] for f in gate_result["failed"]])
        raise ValueError(f"CI gate failed for SHA {gate_result['sha']}. Blocked checks: {failed_names}")

    # 2. Build Report Message
    sha = gate_result["sha"]
    pr_url = f"https://github.com/blob/{owner}/{repo}/pull/{pr_number}"
    
    checks_summary = []
    for check in gate_result["required"]:
        status_icon = "✅" if check["conclusion"] == "success" else "❌"
        checks_summary.append(f"- {status_icon} {check['name']}: {check['status']} ({check['conclusion']})")

    cmds_str = "\n".join([f"- `{cmd}`" for cmd in local_commands])
    
    body_md = f"""### 🚀 Ready for Merge Report

**PR:** [#{pr_number}]({pr_url})
**SHA:** `{sha}`

#### 🏗️ CI Status (Gate)
{"\n".join(checks_summary)}
[View Run]({gate_result['url']})

#### 💻 Local Verification
The following commands were run successfully:
{cmds_str}

{f"#### 📝 Notes{chr(10)}{notes}" if notes else ""}

---
*Sent via `send_ready_report` macro.*
"""

    # 3. Send Message
    subject = f"Ready for Merge: PR #{pr_number} ({sha[:7]})"
    am_res = am_client.send_message(
        project_key=project_key,
        sender_name=sender,
        to=recipients,
        subject=subject,
        body_md=body_md
    )

    return {
        "message_sent": True,
        "am_response": am_res,
        "gate_result": gate_result
    }
