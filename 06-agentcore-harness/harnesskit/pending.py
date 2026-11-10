"""Remember an inline function call before acting on it (walkthrough steps D1 and D2).

While an inline function is pending, the harness rejects any new message on that session until it gets the
toolResult for that exact toolUseId. If your app crashes after paying, the restarted app must know which
call was pending. In production this belongs in your own database; the kit uses one JSON file per session.
"""

import json
from pathlib import Path

from harnesskit.stream import ToolCall


class PendingStore:
    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.json"

    def save(self, session_id: str, call: ToolCall) -> None:
        body = {"tool_use_id": call.tool_use_id, "name": call.name, "input": call.input}
        self._path(session_id).write_text(json.dumps(body))

    def load(self, session_id: str) -> ToolCall | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        body = json.loads(path.read_text())
        return ToolCall(body["tool_use_id"], body["name"], body["input"])

    def clear(self, session_id: str) -> None:
        self._path(session_id).unlink(missing_ok=True)
