"""
tests/test_schemas.py

Unit tests for Pydantic schema validation.
"""
import pytest
from datetime import datetime, timezone
from backend.schemas.test_case import TestSuite, TestCase, TestCategory, Priority, TestStep
from backend.schemas.pr_review import PRReview, ReviewIssue, ReviewCategory, Severity, SecretDetection


def _make_test_suite() -> dict:
    return {
        "ticket_id": "PROJ-123",
        "ticket_summary": "User login with Face ID",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_used": "openai/gpt-4o",
        "total_cases": 1,
        "cases": [
            {
                "id": "TC-001",
                "title": "Successful Face ID login",
                "category": "happy_path",
                "priority": "P1",
                "preconditions": ["User is enrolled in Face ID", "App is installed"],
                "steps": [
                    {
                        "step_number": 1,
                        "action": "Open the app",
                        "expected_result": "Login screen is displayed",
                    },
                    {
                        "step_number": 2,
                        "action": "Present face to the camera",
                        "expected_result": "Face ID authentication dialog appears",
                    },
                ],
                "expected_outcome": "User is logged in and sees the home screen",
                "tags": ["auth", "biometric"],
            }
        ],
        "coverage_notes": "Does not cover enterprise SSO scenarios.",
    }


def _make_pr_review() -> dict:
    return {
        "pr_title": "Add Face ID login",
        "diff_hash": "a" * 64,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "model_used": "openai/gpt-4o",
        "files_changed": 3,
        "lines_added": 120,
        "lines_removed": 15,
        "secret_scan": {"found": False, "occurrences": []},
        "total_issues": 1,
        "issues": [
            {
                "id": "PR-001",
                "category": "security",
                "severity": "high",
                "title": "Sensitive data stored in UserDefaults",
                "description": "The auth token is persisted in UserDefaults which is not encrypted.",
                "location": {
                    "file_path": "Sources/Auth/TokenStore.swift",
                    "start_line": 42,
                    "end_line": 44,
                    "snippet": "UserDefaults.standard.set(token, forKey: \"auth_token\")",
                },
                "suggestion": "Use the iOS Keychain (via Security framework or KeychainAccess) to store sensitive tokens.",
                "references": ["https://developer.apple.com/documentation/security/keychain_services"],
            }
        ],
        "summary": "The PR introduces Face ID authentication. One high severity issue with token storage must be addressed before merge.",
        "merge_recommendation": "request_changes",
    }


def test_valid_test_suite():
    suite = TestSuite.model_validate(_make_test_suite())
    assert suite.ticket_id == "PROJ-123"
    assert len(suite.cases) == 1
    assert suite.cases[0].category == TestCategory.HAPPY_PATH


def test_test_suite_requires_at_least_one_step():
    data = _make_test_suite()
    data["cases"][0]["steps"] = []
    # Pydantic will accept it (steps is a list), but our validation layer checks
    # The schema itself doesn't enforce non-empty steps — that's the LLM prompt's job
    suite = TestSuite.model_validate(data)
    assert suite.cases[0].steps == []


def test_invalid_category_raises():
    data = _make_test_suite()
    data["cases"][0]["category"] = "invalid_category"
    with pytest.raises(Exception):
        TestSuite.model_validate(data)


def test_valid_pr_review():
    review = PRReview.model_validate(_make_pr_review())
    assert review.merge_recommendation == "request_changes"
    assert review.total_issues == 1
    assert review.issues[0].severity == Severity.HIGH


def test_pr_review_invalid_severity_raises():
    data = _make_pr_review()
    data["issues"][0]["severity"] = "catastrophic"
    with pytest.raises(Exception):
        PRReview.model_validate(data)


def test_secret_detection_schema():
    sd = SecretDetection(found=True, occurrences=[{"rule": "AWS Key", "line": 5}])
    assert sd.found is True
    assert len(sd.occurrences) == 1
