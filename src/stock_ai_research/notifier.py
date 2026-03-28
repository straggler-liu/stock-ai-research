from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


def send_feishu_webhook(payload: dict, webhook_url: str, *, retries: int = 3, timeout: int = 8) -> bool:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return 200 <= resp.status < 300
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                return False
            time.sleep(0.5 * attempt)
    return False
