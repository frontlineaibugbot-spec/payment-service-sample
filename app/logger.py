import json
import subprocess
import time
from datetime import datetime, timezone

from app.config import ENV, LOKI_PUSH_URL, SERVICE


def push_log(level: str, message: str, extra: dict | None = None) -> None:
    """Push a log line to Loki via curl."""
    ts_ns = str(int(time.time() * 1_000_000_000))
    line = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": SERVICE,
        "msg": message,
        **(extra or {}),
    })
    payload = json.dumps({
        "streams": [
            {
                "stream": {"app": SERVICE, "level": level, "env": ENV},
                "values": [[ts_ns, line]],
            }
        ]
    })
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                LOKI_PUSH_URL,
                "-H", "Content-Type: application/json",
                "-d", payload,
            ],
            timeout=3,
            check=False,
            capture_output=True,
        )
        print(result)
        if result.returncode == 0:
            print(f"Pushed: {message}")
        else:
            print(f"Loki push failed (exit {result.returncode}): {result.stderr.decode().strip()}")
    except Exception as e:
        print(f"Loki push error: {e}")
