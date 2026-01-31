from typing import Any, Optional, Protocol

from mcp_agent_mail.config import get_settings
from mcp_agent_mail.macros.ci_gate import ci_gate


class AMClientProtocol(Protocol):
    def send_message(
        self,
        project_key: str,
        sender_name: str,
        to: list[str],
        subject: str,
        body_md: str,
    ) -> dict[str, Any]: ...

class RealAMClient:
    """Real implementation using MCP Agent Mail tools via curl."""

    def send_message(
        self,
        project_key: str,
        sender_name: str,
        to: list[str],
        subject: str,
        body_md: str,
    ) -> dict[str, Any]:
        import json
        import subprocess

        settings = get_settings()
        bearer = settings.http.bearer_token or ""
        base = settings.http.host or "127.0.0.1"
        port = settings.http.port
        path = settings.http.path or "/mcp/"
        if not path.startswith("/"):
            path = f"/{path}"
        if not path.endswith("/"):
            path = f"{path}/"

        payload: dict[str, Any] = {
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
                    "body_md": body_md,
                },
            },
        }

        cmd = [
            "curl",
            "-s",
            "-X",
            "POST",
            f"http://{base}:{port}{path}",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(payload),
        ]
        if bearer:
            cmd.extend(["-H", f"Authorization: Bearer {bearer}"])

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)


def _format_check_line(check: dict[str, Any]) -> str:
    conclusion = check.get("conclusion")
    status = check.get("status")
    icon = "✅" if conclusion == "success" else "❌"
    return f"- {icon} {check['name']}: {status} ({conclusion})"


def _pr_url(owner: str, repo: str, pr_number: int) -> str:
    return f"https://github.com/{owner}/{repo}/pull/{pr_number}"

def send_ready_report(
    project_key: str,
    sender: str,
    recipients: list[str],
    owner: str,
    repo: str,
    pr_number: int,
    local_commands: list[str],
    notes: str = "",
    am_client: Optional[AMClientProtocol] = None,
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
    pr_url = _pr_url(owner, repo, pr_number)

    checks_summary = "\n".join([_format_check_line(check) for check in gate_result["required"]])
    cmds_str = "\n".join([f"- `{cmd}`" for cmd in local_commands])
    run_links = "\n".join([f"- {url}" for url in gate_result.get("urls", [])])
    notes_block = f"#### 📝 Notes\n{notes}\n" if notes else ""
    runs_block = f"\n#### 🔗 CI Runs\n{run_links}\n" if run_links else ""

    body_md = (
        "### 🚀 Ready for Merge Report\n\n"
        f"**PR:** [#{pr_number}]({pr_url})\n"
        f"**SHA:** `{sha}`\n\n"
        "#### 🏗️ CI Status (Gate)\n"
        f"{checks_summary}\n"
        f"{runs_block}\n"
        "#### 💻 Local Verification\n"
        "The following commands were run successfully:\n"
        f"{cmds_str}\n\n"
        f"{notes_block}"
        "---\n"
        "*Sent via `send_ready_report` macro.*\n"
    )

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
