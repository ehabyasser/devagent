"""
tools/jira_tool.py

Fetches a Jira ticket via the Jira REST API v3.
Security notes:
  - Uses Basic Auth with an API token (never a password).
  - Never executes shell commands.
  - Validates that the ticket ID matches expected format before making the request.
  - Strips any HTML in description fields.
"""
from __future__ import annotations

import re
import html
from dataclasses import dataclass
from typing import Optional

import httpx

from backend.config import settings


# A valid Jira ticket is PROJECT-NUMBER, e.g. PROJ-123 or MYAPP-4500
_TICKET_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


@dataclass
class JiraTicket:
    id: str
    summary: str
    description: str
    issue_type: str
    status: str
    acceptance_criteria: str
    labels: list[str]


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities (Jira sometimes returns HTML)."""
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text).strip()


def _extract_adf_text(adf: Optional[dict]) -> str:
    """
    Recursively extract plain text from Atlassian Document Format (ADF).
    ADF is the structured JSON format Jira uses for rich text fields.
    """
    if adf is None:
        return ""

    texts: list[str] = []

    def _walk(node: dict) -> None:
        if node.get("type") == "text":
            texts.append(node.get("text", ""))
        for child in node.get("content", []):
            _walk(child)

    _walk(adf)
    return " ".join(texts).strip()


def _extract_acceptance_criteria(description_adf: Optional[dict]) -> str:
    """
    Look for a heading containing 'acceptance criteria' and extract
    the content below it as plain text.
    """
    if description_adf is None:
        return ""

    found = False
    criteria_parts: list[str] = []

    for node in description_adf.get("content", []):
        if node.get("type") == "heading":
            heading_text = _extract_adf_text(node).lower()
            found = "acceptance criteria" in heading_text or "ac:" in heading_text
        elif found:
            if node.get("type") == "heading":
                break  # Next heading encountered — stop
            criteria_parts.append(_extract_adf_text(node))

    return " ".join(criteria_parts).strip()


async def fetch_jira_ticket(ticket_id: str) -> JiraTicket:
    """
    Fetch a Jira ticket by ID and return a structured JiraTicket.

    Raises:
        ValueError: If ticket_id format is invalid.
        httpx.HTTPStatusError: If the Jira API returns an error.
    """
    ticket_id = ticket_id.strip().upper()
    if not _TICKET_RE.match(ticket_id):
        raise ValueError(
            f"Invalid Jira ticket ID format: '{ticket_id}'. "
            "Expected format: PROJECT-123"
        )

    if not settings.jira_base_url or not settings.jira_api_token:
        raise ValueError(
            "JIRA_BASE_URL and JIRA_API_TOKEN must be set in the environment."
        )

    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{ticket_id}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            url,
            auth=(settings.jira_email, settings.jira_api_token),
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()

    data = resp.json()
    fields = data.get("fields", {})
    description_adf = fields.get("description")

    return JiraTicket(
        id=ticket_id,
        summary=fields.get("summary", ""),
        description=_extract_adf_text(description_adf),
        issue_type=fields.get("issuetype", {}).get("name", "Story"),
        status=fields.get("status", {}).get("name", "Unknown"),
        acceptance_criteria=_extract_acceptance_criteria(description_adf),
        labels=fields.get("labels", []),
    )
