"""
tools/diff_parser.py

Parses a unified git diff into a structured representation without
executing any shell commands. Uses pure Python string parsing.

Tradeoff: unidiff library vs. manual parsing.
  - unidiff gives a clean object model (PatchedFile, Hunk, Line).
  - Manual parsing is zero-dependency but fragile.
  - Decision: use unidiff for correctness; it's a small, well-tested library.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib

import unidiff


@dataclass
class DiffSummary:
    diff_hash: str
    files_changed: int
    lines_added: int
    lines_removed: int
    file_summaries: list[dict]   # [{path, added, removed, hunks}]
    truncated_diff: str          # First 8 KB for the LLM prompt


_MAX_DIFF_CHARS = 8_000  # Approx 2K tokens — enough context without overflow


def parse_diff(raw_diff: str) -> DiffSummary:
    """
    Parse a raw unified diff string.

    Args:
        raw_diff: The full text of a git diff.

    Returns:
        DiffSummary with metadata and a truncated version for LLM prompting.

    Raises:
        ValueError: If the diff is empty or not parseable.
    """
    raw_diff = raw_diff.strip()
    if not raw_diff:
        raise ValueError("Diff is empty.")

    diff_hash = hashlib.sha256(raw_diff.encode()).hexdigest()

    try:
        patch_set = unidiff.PatchSet.from_string(raw_diff)
    except Exception as exc:
        raise ValueError(f"Could not parse diff: {exc}") from exc

    total_added = 0
    total_removed = 0
    file_summaries = []

    for patched_file in patch_set:
        added = patched_file.added
        removed = patched_file.removed
        total_added += added
        total_removed += removed
        file_summaries.append({
            "path": patched_file.path,
            "added": added,
            "removed": removed,
            "is_binary": patched_file.is_binary_file,
            "hunks": len(patched_file),
        })

    # Truncate the diff for the LLM to avoid token overflow.
    # Strategy: include as many complete lines as possible up to the limit.
    if len(raw_diff) > _MAX_DIFF_CHARS:
        truncated = raw_diff[:_MAX_DIFF_CHARS]
        # Don't cut mid-line
        truncated = truncated[: truncated.rfind("\n") + 1]
        truncated += "\n\n[... diff truncated — showing first 8 KB ...]"
    else:
        truncated = raw_diff

    return DiffSummary(
        diff_hash=diff_hash,
        files_changed=len(patch_set),
        lines_added=total_added,
        lines_removed=total_removed,
        file_summaries=file_summaries,
        truncated_diff=truncated,
    )
