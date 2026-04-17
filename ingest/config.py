from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "EgoCollect"

DRIVE_MIRROR_FOLDER_ID = "1BcJ1AqLkhD5I8DVt2bFrA6UvfUBmoJQI"

SSD_FULL_THRESHOLD_PERCENT = 10.0

MAX_COPY_WORKERS = 6


@dataclass(frozen=True)
class AppPaths:
    support_dir: Path
    ledger_path: Path
    log_path: Path
    drive_credentials_path: Path
    drive_token_path: Path


def app_paths() -> AppPaths:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    else:
        base = Path.home() / ".config" / APP_NAME.lower()
    base.mkdir(parents=True, exist_ok=True)
    return AppPaths(
        support_dir=base,
        ledger_path=base / "ledger.json",
        log_path=base / "ingest.log",
        drive_credentials_path=base / "drive_credentials.json",
        drive_token_path=base / "drive_token.json",
    )
