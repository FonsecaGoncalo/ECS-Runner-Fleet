from __future__ import annotations

import json
import urllib.request
import hashlib
import hmac

from config import Settings


def get_runner_token(settings: Settings) -> str:
    url = (
        f"https://api.github.com/repos/{settings.github_repo}/actions/"
        "runners/registration-token"
    )
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"token {settings.github_pat}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    return data["token"]

def verify_github_signature(body: bytes, secret: str, signature: str) -> bool:
    """Verify GitHub webhook signature (X-Hub-Signature-256)."""
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
