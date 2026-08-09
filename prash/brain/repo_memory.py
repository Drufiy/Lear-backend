"""Ported from prash-backend/app/agent/repo_memory.py (2026-08-09, Track D days 4-5)
-- PARTIALLY. Only the pure RepoMemory dataclass and its as_prompt_context()/
is_empty() formatting are ported.

PRASH_V2.md §4's architecture table listed this file as "Zero" coupling to the
hosted stack -- that was wrong, caught while actually reading the file: every
_fetch_* helper and build_repo_memory() itself queries `supabase.table(...)`
directly. v2 has no database by design (§4/§7), so none of that ports.

diagnose_failure() already treats repo_memory as a fully optional parameter
(defaults to None, every call site checks truthiness before using it) --
nothing in diagnosis_agent.py needed to change to accommodate dropping the
DB-backed builder. Callers in v2 just never pass repo_memory; the type stays
importable so the signature/prompt-formatting logic remains available if a
local (non-Supabase) memory source gets built later.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RepoMemory:
    repo_id: str
    similar_fixes: list[dict[str, Any]] = field(default_factory=list)
    repeated_error_signatures: list[dict[str, Any]] = field(default_factory=list)
    flaky_tests: list[dict[str, Any]] = field(default_factory=list)
    category_outcomes: dict[str, dict[str, Any]] = field(default_factory=dict)
    known_good_files: list[dict[str, Any]] = field(default_factory=list)
    dependency_patterns: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            (
                self.similar_fixes,
                self.repeated_error_signatures,
                self.flaky_tests,
                self.category_outcomes,
                self.known_good_files,
                self.dependency_patterns,
            )
        )

    def as_prompt_context(self) -> str:
        if self.is_empty():
            return ""

        lines = [
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "REPO MEMORY (learned from this repository's previous CI failures and fixes)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        if self.category_outcomes:
            lines.append("\nHistorical outcomes by category:")
            for category, stats in sorted(self.category_outcomes.items()):
                attempts = stats.get("attempts", 0)
                verified = stats.get("verified", 0)
                exhausted = stats.get("exhausted", 0)
                rate = stats.get("verified_rate")
                rate_text = f"{int(rate * 100)}%" if isinstance(rate, float) else "unknown"
                lines.append(
                    f"- {category}: {verified}/{attempts} verified ({rate_text}), "
                    f"{exhausted} exhausted"
                )

        if self.repeated_error_signatures:
            lines.append("\nRepeated failure signatures:")
            for item in self.repeated_error_signatures:
                lines.append(
                    f"- signature={item.get('error_signature')} seen {item.get('count')}x, "
                    f"last category={item.get('last_category') or 'unknown'}, "
                    f"last status={item.get('last_status') or 'unknown'}"
                )

        if self.dependency_patterns:
            lines.append("\nDependency patterns that previously mattered:")
            for item in self.dependency_patterns:
                files = ", ".join(item.get("files", [])[:5]) or "unknown files"
                lines.append(f"- {item.get('summary', '')[:220]} (files: {files})")

        if self.flaky_tests:
            lines.append("\nKnown flaky tests:")
            for item in self.flaky_tests[:8]:
                test_name = item.get("test_name") or "*"
                lines.append(
                    f"- {item.get('test_file')}::{test_name}, "
                    f"failures={item.get('fail_count')}, pass-after-retry={item.get('pass_after_retry_count')}"
                )

        if self.known_good_files:
            lines.append("\nKnown-good files available for diff-risk comparison:")
            for item in self.known_good_files[:10]:
                lines.append(f"- {item.get('file_path')} verified_at={item.get('verified_at') or 'unknown'}")

        if self.similar_fixes:
            lines.append("\nRecent verified fixes from this repo:")
            for i, fix in enumerate(self.similar_fixes, 1):
                files_summary = ", ".join(
                    f.get("path", "") for f in (fix.get("files_changed") or []) if isinstance(f, dict)
                ) or "none"
                lines.append(
                    f"\nVerified Fix #{i} [{fix.get('category', '?')}] "
                    f"(confidence {int((fix.get('confidence') or 0) * 100)}%)"
                )
                lines.append(f"Problem: {fix.get('problem_summary', '')[:300]}")
                lines.append(f"Root cause: {fix.get('root_cause', '')[:300]}")
                lines.append(f"Fix: {fix.get('fix_description', '')[:300]}")
                lines.append(f"Files changed: {files_summary}")

        lines.append(
            "\nUse this memory as a prior, not as proof. If current logs contradict memory, trust the logs."
        )
        return "\n".join(lines)
