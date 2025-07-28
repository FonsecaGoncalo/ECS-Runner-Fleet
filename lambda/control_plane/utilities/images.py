from __future__ import annotations

import re


def sanitize_image_label(label: str) -> str:
    """Sanitize a label so it can be used as an ECR tag or ECS family name."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", label)
