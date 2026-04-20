from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SyncOutbox:
    """Append-only JSONL queue of pending sync operations.

    Every push the app wants to send to Drive is appended here first. The
    sync worker drains the file when online and removes entries on success.
    Survives app restarts and offline periods.
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, op: str, args: dict) -> str:
        entry = {
            "id": uuid.uuid4().hex,
            "created_at": _now(),
            "op": op,
            "args": args,
        }
        with self._lock:
            if op == "upsert_ssd":
                ssd_uuid = (args.get("manifest") or {}).get("ssd_uuid")
                if ssd_uuid:
                    self._drop_prior_upserts_unsafe(ssd_uuid)
            with self.path.open("a") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")
        return entry["id"]

    def read_all(self) -> list[dict]:
        with self._lock:
            return self._read_all_unsafe()

    def remove_ids(self, ids: set[str]) -> None:
        if not ids:
            return
        with self._lock:
            kept_lines = []
            for entry in self._read_all_unsafe():
                if entry.get("id") in ids:
                    continue
                kept_lines.append(json.dumps(entry, default=str))
            self._write_lines_unsafe(kept_lines)

    def count(self) -> int:
        return len(self.read_all())

    def _read_all_unsafe(self) -> list[dict]:
        if not self.path.exists():
            return []
        entries = []
        try:
            with self.path.open("r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return entries

    def _write_lines_unsafe(self, lines: list[str]) -> None:
        tmp = self.path.with_suffix(".jsonl.tmp")
        with tmp.open("w") as fh:
            for line in lines:
                fh.write(line + "\n")
        tmp.replace(self.path)

    def _drop_prior_upserts_unsafe(self, ssd_uuid: str) -> None:
        entries = self._read_all_unsafe()
        kept_lines = []
        dropped = False
        for entry in entries:
            if entry.get("op") == "upsert_ssd":
                m = (entry.get("args") or {}).get("manifest") or {}
                if m.get("ssd_uuid") == ssd_uuid:
                    dropped = True
                    continue
            kept_lines.append(json.dumps(entry, default=str))
        if dropped:
            self._write_lines_unsafe(kept_lines)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
