from __future__ import annotations

import hashlib
import hmac


def verify_github_signature(body: bytes, secret: str, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    expected = (
        "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    )  
    return hmac.compare_digest(expected, signature)
