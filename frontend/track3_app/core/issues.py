"""Append integration issues to INTEGRATION_ISSUES.md at repo root, deduplicated.

Only real (non-fixture) data is logged, so synthetic fixtures never pollute the shared file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from . import config

log = logging.getLogger("spoonbill.issues")


def log_issue(message: str, *, enabled: bool, path: Path | None = None) -> bool:
    """Returns True when a new line was written. Duplicate messages are skipped."""
    if not enabled:
        log.info("integration issue (not written, fixture mode): %s", message)
        return False
    target = Path(path or config.INTEGRATION_ISSUES_PATH)
    existing = target.read_text(encoding="utf-8") if target.is_file() else "# Integration issues\n\n"
    if message in existing:
        return False
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(existing.rstrip("\n") + f"\n- [auto] {stamp} (track3 UI): {message}\n")
    return True
