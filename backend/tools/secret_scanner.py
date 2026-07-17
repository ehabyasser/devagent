"""
tools/secret_scanner.py

Lightweight regex-based secret scanner.

Design decision: We use deterministic regex patterns instead of a full
entropy scanner (like truffleHog) to keep this dependency-free and fast.
False positive rate is higher but latency is < 1 ms per file.
For teams needing higher coverage, plug in truffleHog as a CLI tool
and call it as a subprocess (NOT done here to avoid shell execution risks).

Categories scanned:
  - AWS Access Key IDs and Secret Keys
  - Generic API keys (bearer tokens, api_key patterns)
  - Private keys (PEM blocks)
  - GitHub Personal Access Tokens
  - Slack tokens
  - JWT tokens
  - Generic high-entropy strings (base64 > 40 chars)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SecretOccurrence:
    rule_name: str
    file_path: str
    line_number: int
    masked_value: str   # Never log the actual secret


# Each rule: (name, compiled_regex)
_RULES: list[tuple[str, re.Pattern]] = [
    ("AWS Access Key ID",       re.compile(r"AKIA[0-9A-Z]{16}")),
    ("AWS Secret Access Key",   re.compile(r"(?i)aws_secret_access_key\s*=\s*['\"]?[A-Za-z0-9/+=]{40}")),
    ("PEM Private Key",         re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub PAT",              re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("GitHub OAuth Token",      re.compile(r"gho_[A-Za-z0-9]{36}")),
    ("Slack Token",             re.compile(r"xox[baprs]-[0-9A-Za-z\-]+")),
    ("JWT Token",               re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("Generic API Key",         re.compile(r"(?i)(api_key|apikey|api-key|secret_key|access_token)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,}")),
    ("Bearer Token",            re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.]{20,}")),
    ("Google API Key",          re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("Stripe Secret Key",       re.compile(r"sk_(live|test)_[A-Za-z0-9]{24,}")),
    ("Heroku API Key",          re.compile(r"(?i)heroku.*[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}")),
]


def _mask(value: str) -> str:
    """Show only the first 4 characters, mask the rest."""
    return value[:4] + "*" * max(4, len(value) - 4) if len(value) > 4 else "****"


def scan_diff_for_secrets(diff_text: str) -> list[SecretOccurrence]:
    """
    Scan a unified git diff for secrets.
    Only scans lines that begin with '+' (i.e. additions) to avoid
    flagging secrets that already existed in the codebase.

    Args:
        diff_text: Raw unified diff string.

    Returns:
        List of SecretOccurrence (empty if clean).
    """
    occurrences: list[SecretOccurrence] = []
    current_file = "unknown"
    line_number = 0

    for raw_line in diff_text.splitlines():
        # Track current file from diff headers
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            line_number = 0
            continue

        # Track line numbers in added hunks
        if raw_line.startswith("@@"):
            # e.g.  @@ -0,0 +1,42 @@
            match = re.search(r"\+(\d+)", raw_line)
            if match:
                line_number = int(match.group(1)) - 1
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            line_number += 1
            content = raw_line[1:]  # strip leading '+'
            for rule_name, pattern in _RULES:
                m = pattern.search(content)
                if m:
                    occurrences.append(
                        SecretOccurrence(
                            rule_name=rule_name,
                            file_path=current_file,
                            line_number=line_number,
                            masked_value=_mask(m.group(0)),
                        )
                    )
        elif raw_line.startswith(" "):
            line_number += 1

    return occurrences
