import argparse
import json
import sys

from mcp_agent_mail.macros.ci_gate import ci_gate
from mcp_agent_mail.macros.send_ready_report import send_ready_report


def main():
    parser = argparse.ArgumentParser(description="MCP Agent Mail Macros CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ci_gate
    gate_parser = subparsers.add_parser("ci_gate", help="Check CI status")
    gate_parser.add_argument("--owner", required=True)
    gate_parser.add_argument("--repo", required=True)
    gate_parser.add_argument("--pr", type=int, help="PR number")
    gate_parser.add_argument("--sha", help="Commit SHA")
    gate_parser.add_argument("--checks", nargs="+", default=["Fast Tests (ubuntu)"], help="Required checks")

    # send_ready_report
    report_parser = subparsers.add_parser("send_ready_report", help="Send ready report if CI is green")
    report_parser.add_argument("--project", required=True)
    report_parser.add_argument("--sender", required=True)
    report_parser.add_argument("--to", nargs="+", required=True)
    report_parser.add_argument("--owner", required=True)
    report_parser.add_argument("--repo", required=True)
    report_parser.add_argument("--pr", type=int, required=True)
    report_parser.add_argument("--cmds", nargs="+", required=True, help="Local commands run")
    report_parser.add_argument("--notes", default="")

    args = parser.parse_args()

    if args.command == "ci_gate":
        try:
            res = ci_gate(
                owner=args.owner,
                repo=args.repo,
                pr_number=args.pr,
                sha=args.sha,
                require_checks=args.checks
            )
            print(json.dumps(res, indent=2))
            sys.exit(0 if res["ok"] else 1)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, indent=2))
            sys.exit(1)

    elif args.command == "send_ready_report":
        try:
            res = send_ready_report(
                project_key=args.project,
                sender=args.sender,
                recipients=args.to,
                owner=args.owner,
                repo=args.repo,
                pr_number=args.pr,
                local_commands=args.cmds,
                notes=args.notes
            )
            print(json.dumps(res, indent=2))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}, indent=2))
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
