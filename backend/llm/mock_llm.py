"""
llm/mock_llm.py

Mock LLM provider for local testing and offline demos.
Returns realistic structured JSON matching Pydantic schemas.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncIterator, Optional
from .base_llm import BaseLLM

class MockLLM(BaseLLM):
    @property
    def model_name(self) -> str:
        return "mock/devagent-simulator"

    async def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[str] = None,
    ) -> str:
        # Determine the user request type by scanning the messages
        prompt_text = ""
        for m in messages:
            if m["role"] == "user":
                prompt_text += m["content"] + "\n"

        # Check if it looks like a Test Case generation request
        if "TestSuite" in prompt_text or "test" in prompt_text.lower() or "acceptance criteria" in prompt_text.lower():
            return self._mock_test_suite(prompt_text)
        else:
            return self._mock_pr_review(prompt_text)

    async def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        # Simple async generator that yields the full text in large chunks
        full_text = await self.complete(messages)
        # Yield in chunks of 50 characters to simulate speed
        chunk_size = 50
        for i in range(0, len(full_text), chunk_size):
            yield full_text[i : i + chunk_size]

    def _mock_test_suite(self, prompt: str) -> str:
        # Check if it's Face ID
        is_faceid = "face id" in prompt.lower() or "biometric" in prompt.lower()
        is_checkout = "checkout" in prompt.lower() or "payment" in prompt.lower() or "apple pay" in prompt.lower()

        ticket_id = "PROJ-123"
        ticket_summary = "Implement Face ID Login" if is_faceid else ("Implement Payment Checkout" if is_checkout else "Feature Implementation")

        cases = []
        if is_faceid:
            cases = [
                {
                    "id": "TC-001",
                    "title": "Successful Login using Face ID",
                    "category": "happy_path",
                    "priority": "P0",
                    "preconditions": [
                        "Face ID is enrolled and enabled in device settings",
                        "User is registered and has completed a password login previously"
                    ],
                    "steps": [
                        {"step_number": 1, "action": "Launch the application", "expected_result": "App displays Face ID prompt request"},
                        {"step_number": 2, "action": "Present enrolled face to sensor", "expected_result": "Face ID authentication succeeds"},
                        {"step_number": 3, "action": "Observe app navigation", "expected_result": "User lands on Home Screen within 2 seconds"}
                    ],
                    "expected_outcome": "User is successfully authenticated and directed to the home screen.",
                    "tags": ["biometrics", "happy-path", "ios"]
                },
                {
                    "id": "TC-002",
                    "title": "Face ID failed attempt limits and password fallback",
                    "category": "negative",
                    "priority": "P0",
                    "preconditions": [
                        "Face ID is enrolled",
                        "App is launched showing the Face ID prompt"
                    ],
                    "steps": [
                        {"step_number": 1, "action": "Fail Face ID authentication 3 consecutive times", "expected_result": "App dismisses Face ID prompt"},
                        {"step_number": 2, "action": "Observe login options displayed", "expected_result": "App displays password input fields fallback"},
                        {"step_number": 3, "action": "Enter valid password and tap Log In", "expected_result": "Login succeeds and home screen displays"}
                    ],
                    "expected_outcome": "After 3 failures, user is forced to fallback to password authentication.",
                    "tags": ["fallback", "security"]
                },
                {
                    "id": "TC-003",
                    "title": "Device without Face ID support",
                    "category": "boundary",
                    "priority": "P1",
                    "preconditions": [
                        "Device does not support Face ID (e.g. iPad without Face ID)"
                    ],
                    "steps": [
                        {"step_number": 1, "action": "Launch the app and open settings", "expected_result": "Face ID settings toggle is hidden"},
                        {"step_number": 2, "action": "Attempt to trigger authentication", "expected_result": "App defaults immediately to password entry"}
                    ],
                    "expected_outcome": "No Face ID features are presented on unsupported devices.",
                    "tags": ["compatibility", "boundary-cases"]
                }
            ]
        elif is_checkout:
            cases = [
                {
                    "id": "TC-001",
                    "title": "Successful Checkout with Credit Card",
                    "category": "happy_path",
                    "priority": "P0",
                    "preconditions": [
                        "User has items in the cart",
                        "User is logged in"
                    ],
                    "steps": [
                        {"step_number": 1, "action": "Tap checkout and select Credit Card", "expected_result": "Credit card entry sheet is presented"},
                        {"step_number": 2, "action": "Enter valid Visa card details and tap Pay", "expected_result": "Payment processing loading spinner appears"},
                        {"step_number": 3, "action": "Observe post-payment screen", "expected_result": "App displays order confirmation and unique Order ID"}
                    ],
                    "expected_outcome": "Order is successfully completed and cart is emptied.",
                    "tags": ["checkout", "payment", "visa"]
                },
                {
                    "id": "TC-002",
                    "title": "Declined card error handling",
                    "category": "negative",
                    "priority": "P1",
                    "preconditions": [
                        "User has items in the cart and is on the payment sheet"
                    ],
                    "steps": [
                        {"step_number": 1, "action": "Enter a credit card details that triggers decline", "expected_result": "Declined card warning label appears"},
                        {"step_number": 2, "action": "Check the cart status", "expected_result": "Cart items are retained; user can retry payment"}
                    ],
                    "expected_outcome": "User is informed of the decline reason and can change payment method.",
                    "tags": ["payment-failure", "declined"]
                }
            ]
        else:
            cases = [
                {
                    "id": "TC-001",
                    "title": "Generic Feature Happy Path Verification",
                    "category": "happy_path",
                    "priority": "P0",
                    "preconditions": ["User has access to the feature"],
                    "steps": [
                        {"step_number": 1, "action": "Trigger the main feature path", "expected_result": "Feature completes successfully without errors"},
                        {"step_number": 2, "action": "Verify stored data", "expected_result": "State is correctly saved in database"}
                    ],
                    "expected_outcome": "Feature performs its core function correctly.",
                    "tags": ["happy-path", "core"]
                },
                {
                    "id": "TC-002",
                    "title": "Feature Invalid Parameter Inputs",
                    "category": "negative",
                    "priority": "P1",
                    "preconditions": ["User is on input screen"],
                    "steps": [
                        {"step_number": 1, "action": "Input blank or invalid parameters", "expected_result": "Validation labels are displayed instantly"},
                        {"step_number": 2, "action": "Tap submit", "expected_result": "Action is blocked; no network calls are dispatched"}
                    ],
                    "expected_outcome": "App safely catches incorrect input parameters and prevents submission.",
                    "tags": ["validation", "negative"]
                }
            ]

        suite = {
            "ticket_id": ticket_id,
            "ticket_summary": ticket_summary,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_used": self.model_name,
            "total_cases": len(cases),
            "cases": cases,
            "coverage_notes": "Database level constraints and network timeout conditions are not covered by these black-box UI test cases."
        }
        return json.dumps(suite)

    def _mock_pr_review(self, prompt: str) -> str:
        # Check if it has secrets
        is_secrets = "stripe" in prompt.lower() or "amplitudeapikey" in prompt.lower() or "secret" in prompt.lower()
        is_auth = "authmanager" in prompt.lower() or "biometrics" in prompt.lower()

        issues = []
        if is_auth:
            issues = [
                {
                    "id": "PR-001",
                    "category": "swift_best_practices",
                    "severity": "high",
                    "title": "MainActor missing on class level or properties",
                    "description": "AuthManager publishes state changes on `@Published var isAuthenticated`. If functions modifying this property are run on background threads, SwiftUI will throw runtime warnings.",
                    "location": {
                        "file_path": "Sources/Auth/AuthManager.swift",
                        "start_line": 8,
                        "end_line": 8,
                        "snippet": "class AuthManager: ObservableObject {"
                    },
                    "suggestion": "Mark `class AuthManager` with `@MainActor` or wrap state changes in `Task { @MainActor in ... }`.",
                    "references": [
                        "https://github.com/apple/swift-evolution/blob/main/proposals/0316-global-actors.md"
                    ]
                },
                {
                    "id": "PR-002",
                    "category": "architecture",
                    "severity": "medium",
                    "title": "Shared Singleton instance violates Dependency Injection",
                    "description": "Exposing `static let shared = AuthManager()` makes testing difficult by coupling classes tightly to this global instance.",
                    "location": {
                        "file_path": "Sources/Auth/AuthManager.swift",
                        "start_line": 9,
                        "end_line": 9,
                        "snippet": "static let shared = AuthManager()"
                    },
                    "suggestion": "Use dependency injection via initializer arguments, allowing mock instances to be injected in unit tests.",
                    "references": []
                }
            ]
        elif is_secrets:
            issues = [
                {
                    "id": "PR-001",
                    "category": "security",
                    "severity": "critical",
                    "title": "Hardcoded Amplitude API Key",
                    "description": "Hardcoding high-privilege keys like `amplitudeAPIKey` inside source files leaks keys to git history and unauthorised personnel.",
                    "location": {
                        "file_path": "Sources/Analytics/Config.swift",
                        "start_line": 4,
                        "end_line": 4,
                        "snippet": "static let amplitudeAPIKey     = \"abc123secretkey9876543210abcdef\""
                    },
                    "suggestion": "Load this key at runtime using a Configuration PLIST or from environment variables during CI build phase.",
                    "references": [
                        "https://owasp.org/www-community/Source_Code_Analysis_Tools"
                    ]
                }
            ]
        else:
            issues = [
                {
                    "id": "PR-001",
                    "category": "swift_best_practices",
                    "severity": "high",
                    "title": "Use of force unwrapping",
                    "description": "Using force unwrap operator `!` can crash the application at runtime if the value is nil.",
                    "location": {
                        "file_path": "Sources/Networking/APIClient.swift",
                        "start_line": 20,
                        "end_line": 20,
                        "snippet": "var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: true)!"
                    },
                    "suggestion": "Safely unwrap components using `guard let` or handle the nil option cleanly.",
                    "references": []
                }
            ]

        # Scan for secrets in prompt
        secret_found = "secretkey" in prompt.lower() or "token_" in prompt.lower()
        secret_occurrences = []
        if secret_found:
            secret_occurrences = [
                {
                    "rule": "High-entropy API key",
                    "file": "Sources/Analytics/Config.swift",
                    "line": 4,
                    "masked_value": "abc123se*********"
                }
            ]

        review = {
            "pr_title": "PR Review",
            "diff_hash": "a1b2c3d4e5f6g7h8i9j0",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "model_used": self.model_name,
            "files_changed": 2,
            "lines_added": 40,
            "lines_removed": 5,
            "secret_scan": {
                "found": secret_found,
                "occurrences": secret_occurrences
            },
            "total_issues": len(issues),
            "issues": issues,
            "summary": "This PR implements clean structures, but contains a few Swift best practice violations and code styling anomalies that should be resolved before merge.",
            "merge_recommendation": "request_changes" if len(issues) > 0 else "approve"
        }
        return json.dumps(review)
