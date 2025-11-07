from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_CACHE_ROOT = Path("output/cache")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _profile_hash(profile: Dict[str, Any]) -> str:
    data = json.dumps(profile, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(data).hexdigest()[:12]


def cache_dir_for_bv(bv_id: str, root: Optional[Path] = None) -> Path:
    if root is None:
        root = DEFAULT_CACHE_ROOT
    return root / bv_id


def save_result(bv_id: str, profile: Dict[str, Any], payload: Dict[str, Any], root: Optional[Path] = None) -> Path:
    d = cache_dir_for_bv(bv_id, root)
    _ensure_dir(d)
    h = _profile_hash(profile)
    result_path = d / f"result_{h}.json"
    result_path.write_text(json.dumps({"profile": profile, "data": payload}, ensure_ascii=False, indent=2), encoding="utf-8")
    # Also update latest pointer (simple copy)
    latest = d / "result_latest.json"
    latest.write_text(json.dumps({"profile": profile, "data": payload}, ensure_ascii=False, indent=2), encoding="utf-8")

    # Update meta index (append unique hash)
    meta_path = d / "meta.json"
    meta = {"profiles": []}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {"profiles": []}
    if h not in meta.get("profiles", []):
        meta.setdefault("profiles", []).append(h)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return result_path


def load_latest(bv_id: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    p = cache_dir_for_bv(bv_id, root) / "result_latest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_by_profile(bv_id: str, profile: Dict[str, Any], root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    d = cache_dir_for_bv(bv_id, root)
    h = _profile_hash(profile)
    p = d / f"result_{h}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
