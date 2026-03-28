from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class LiveGate:
    def __init__(self, state_file: str = "data/live_gate_state.json") -> None:
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.state_file.exists():
            self._write({"paused": False, "reason": "", "updated_at": ""})

    def _read(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def _write(self, payload: dict) -> None:
        self.state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def status(self) -> dict:
        return self._read()

    def pause(self, reason: str) -> dict:
        payload = {
            "paused": True,
            "reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write(payload)
        return payload

    def resume(self) -> dict:
        payload = {
            "paused": False,
            "reason": "manual_resume",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write(payload)
        return payload
