from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

BV_REGEX = re.compile(r"BV[0-9A-Za-z]+")
SUB_EXTS = (".srt", ".ass", ".vtt", ".txt", ".json")


def extract_bv_id(text: str) -> Optional[str]:
    if not text:
        return None
    m = BV_REGEX.search(text)
    return m.group(0) if m else None


def derive_bv_from_paths(subs_path: Optional[str], video_path: Optional[str]) -> Optional[str]:
    for p in [subs_path, video_path]:
        if p:
            name = Path(p).name
            bv = extract_bv_id(name)
            if bv:
                return bv
    return None


def find_latest_subs(output_dir: Path) -> Optional[Path]:
    candidates = []
    for ext in SUB_EXTS:
        candidates.extend(output_dir.rglob(f"*{ext}"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]
