"""Local JSON-backed episodic memory for Lear/Prash (PRASH_V2.md, demo task 05).

Stores verified fixes, error signatures, and category outcomes in .prash/memory.json.
No external database dependency — works entirely from the local filesystem.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .repo_memory import RepoMemory


def get_memory_path() -> Path:
    """Return the configured or default path to the local memory JSON file."""
    return Path(os.environ.get("PRASH_MEMORY_PATH", ".prash/memory.json"))


def load_memory(repo_id: str = "default", path: Optional[Path] = None) -> RepoMemory:
    """Load episodic memory from local JSON store.

    Returns a populated RepoMemory dataclass if the store exists, or an empty
    RepoMemory instance if it does not.
    """
    target = path or get_memory_path()
    if not target.exists():
        return RepoMemory(repo_id=repo_id)

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return RepoMemory(repo_id=repo_id)

    return RepoMemory(
        repo_id=repo_id,
        similar_fixes=data.get("similar_fixes", []),
        repeated_error_signatures=data.get("repeated_error_signatures", []),
        flaky_tests=data.get("flaky_tests", []),
        category_outcomes=data.get("category_outcomes", {}),
        known_good_files=data.get("known_good_files", []),
        dependency_patterns=data.get("dependency_patterns", []),
    )


def save_fix(
    diagnosis_summary: Union[Dict[str, Any], Any],
    verified: bool = True,
    path: Optional[Path] = None,
) -> None:
    """Append a fix (and track repeated error signatures + category outcomes)
    to the local JSON memory store.

    Accepts either a plain dictionary or a Pydantic Diagnosis object.
    """
    target = path or get_memory_path()
    data: Dict[str, Any] = {}
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}

    # Convert Pydantic Diagnosis or object if needed
    summary_dict: Dict[str, Any]
    if hasattr(diagnosis_summary, "model_dump"):
        raw = diagnosis_summary.model_dump()
        files_list = []
        for fc in raw.get("files_changed") or []:
            if isinstance(fc, dict):
                files_list.append({"path": fc.get("path"), "explanation": fc.get("explanation")})
        if not files_list and raw.get("config_patch") and raw.get("config_patch_target"):
            for k, v in raw["config_patch"].items():
                files_list.append({
                    "path": f"configmap/{raw['config_patch_target']}",
                    "key": k,
                    "new": v,
                })
        summary_dict = {
            "category": raw.get("category", "unknown"),
            "confidence": raw.get("confidence", 0.9),
            "problem_summary": raw.get("problem_summary", ""),
            "root_cause": raw.get("root_cause", ""),
            "fix_description": raw.get("fix_description", ""),
            "files_changed": files_list,
            "error_signature": raw.get("error_signature"),
            "recommended_action": raw.get("recommended_action"),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    elif isinstance(diagnosis_summary, dict):
        summary_dict = dict(diagnosis_summary)
        if "verified_at" not in summary_dict:
            summary_dict["verified_at"] = datetime.now(timezone.utc).isoformat()
    else:
        summary_dict = {
            "problem_summary": str(diagnosis_summary),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    # 1. Append to similar_fixes
    fixes: List[Dict[str, Any]] = data.setdefault("similar_fixes", [])
    fixes.append(summary_dict)

    # 2. Update repeated_error_signatures
    signatures: List[Dict[str, Any]] = data.setdefault("repeated_error_signatures", [])
    sig = summary_dict.get("error_signature")
    if sig:
        existing = next((s for s in signatures if s.get("error_signature") == sig), None)
        if existing:
            existing["count"] = existing.get("count", 1) + 1
            existing["last_category"] = summary_dict.get("category")
            existing["last_status"] = "verified" if verified else "unverified"
        else:
            signatures.append({
                "error_signature": sig,
                "count": 1,
                "last_category": summary_dict.get("category"),
                "last_status": "verified" if verified else "unverified",
            })

    # 3. Update category_outcomes
    category = summary_dict.get("category")
    if category:
        category_outcomes: Dict[str, Dict[str, Any]] = data.setdefault("category_outcomes", {})
        cat_stats = category_outcomes.setdefault(
            category,
            {"attempts": 0, "verified": 0, "exhausted": 0, "verified_rate": 0.0},
        )
        cat_stats["attempts"] += 1
        if verified:
            cat_stats["verified"] += 1
        else:
            cat_stats["exhausted"] += 1
        if cat_stats["attempts"] > 0:
            cat_stats["verified_rate"] = round(cat_stats["verified"] / cat_stats["attempts"], 2)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def clear_memory(path: Optional[Path] = None) -> None:
    """Clear or delete the local episodic memory store (useful for testing or reset)."""
    target = path or get_memory_path()
    if target.exists():
        target.unlink()
