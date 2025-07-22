import json
import urllib.request


def get_runner_token(repo: str, pat: str) -> str:
    """Request a registration token for a repository runner."""
    url = f"https://api.github.com/repos/{repo}/actions/runners/registration-token"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    return data["token"]
