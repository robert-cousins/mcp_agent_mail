from collections.abc import Iterable
from typing import Any, Optional, Protocol


class GithubClientProtocol(Protocol):
    def get_check_runs(self, owner: str, repo: str, sha: str) -> list[dict[str, Any]]: ...
    def get_pr_head_sha(self, owner: str, repo: str, pr_number: int) -> str: ...

class RealGithubClient:
    """Real implementation using 'gh' CLI."""

    def get_check_runs(self, owner: str, repo: str, sha: str) -> list[dict[str, Any]]:
        import json
        import subprocess

        cmd = ["gh", "api", f"repos/{owner}/{repo}/commits/{sha}/check-runs"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        return payload.get("check_runs", [])

    def get_pr_head_sha(self, owner: str, repo: str, pr_number: int) -> str:
        import subprocess

        cmd = [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            f"{owner}/{repo}",
            "--json",
            "headRefOid",
            "--jq",
            ".headRefOid",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()

def ci_gate(
    owner: str,
    repo: str,
    pr_number: Optional[int] = None,
    sha: Optional[str] = None,
    require_checks: Optional[Iterable[str]] = None,
    allow_skipped: Optional[Iterable[str]] = None,
    require_conclusion: str = "success",
    github_client: Optional[GithubClientProtocol] = None,
) -> dict[str, Any]:
    """
    Assert a PR/commit is "green enough".
    """
    if github_client is None:
        github_client = RealGithubClient()

    required_names = list(require_checks or ["Fast Tests (ubuntu)"])
    allowed_skipped = set(allow_skipped or {"Fast Tests (macos)", "Full Tests"})

    if pr_number is not None:
        resolved_sha = github_client.get_pr_head_sha(owner, repo, pr_number)
    elif sha is not None:
        resolved_sha = sha
    else:
        raise ValueError("Either pr_number or sha must be provided")

    check_runs = github_client.get_check_runs(owner, repo, resolved_sha)

    required_results: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    urls: set[str] = set()

    # Create a map for quick lookup
    checks_map = {run["name"]: run for run in check_runs}

    # Evaluate required checks
    for req_name in required_names:
        if req_name not in checks_map:
            failed.append({"name": req_name, "reason": "missing"})
            continue

        run = checks_map[req_name]
        status = run.get("status")
        conclusion = run.get("conclusion")
        if run.get("html_url"):
            urls.add(run["html_url"])

        required_results.append({
            "name": req_name,
            "status": status,
            "conclusion": conclusion
        })

        if status != "completed" or conclusion != require_conclusion:
            failed.append({
                "name": req_name,
                "status": status,
                "conclusion": conclusion,
                "reason": "unsuccessful"
            })

    # Evaluate other checks
    for name, run in checks_map.items():
        if name in required_names:
            continue

        status = run.get("status")
        conclusion = run.get("conclusion")
        if run.get("html_url"):
            urls.add(run["html_url"])

        others.append({
            "name": name,
            "status": status,
            "conclusion": conclusion
        })

        # If it's not a required check, we still check if it's failed,
        # unless it's in allow_skipped and is skipped.
        if status == "completed":
            if conclusion == require_conclusion:
                continue
            if conclusion == "skipped" and any(name.startswith(s) for s in allowed_skipped):
                continue
            failed.append({
                "name": name,
                "status": status,
                "conclusion": conclusion,
                "reason": "non_success"
            })
        else:
            failed.append({
                "name": name,
                "status": status,
                "conclusion": conclusion,
                "reason": "not_completed"
            })

    required_results.sort(key=lambda item: item["name"])
    others.sort(key=lambda item: item["name"])
    failed.sort(key=lambda item: item["name"])

    return {
        "ok": len(failed) == 0,
        "sha": resolved_sha,
        "required": required_results,
        "others": others,
        "failed": failed,
        "urls": sorted(urls),
    }
