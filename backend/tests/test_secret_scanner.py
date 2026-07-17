"""
tests/test_secret_scanner.py

Unit tests for the secret scanner. These run with zero external dependencies.
"""
import pytest
from backend.tools.secret_scanner import scan_diff_for_secrets


CLEAN_DIFF = """diff --git a/Sources/App/Config.swift b/Sources/App/Config.swift
index abc123..def456 100644
--- a/Sources/App/Config.swift
+++ b/Sources/App/Config.swift
@@ -1,5 +1,6 @@
 import Foundation
+let baseURL = "https://api.example.com"
+let timeoutSeconds = 30
 struct Config {
     static let version = "1.0.0"
 }
"""

AWS_KEY_DIFF = """diff --git a/Sources/App/AWSHelper.swift b/Sources/App/AWSHelper.swift
index abc123..def456 100644
--- a/Sources/App/AWSHelper.swift
+++ b/Sources/App/AWSHelper.swift
@@ -1,3 +1,4 @@
 import Foundation
+let awsKey = "AKIAIOSFODNN7EXAMPLE"
+let secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
 class AWSHelper {}
"""

GITHUB_PAT_DIFF = """diff --git a/CI/deploy.sh b/CI/deploy.sh
index abc123..def456 100644
--- a/CI/deploy.sh
+++ b/CI/deploy.sh
@@ -1,2 +1,3 @@
 #!/bin/bash
+GITHUB_TOKEN=ghp_16C7e42F292c6912E7710c838347Ae178B4a
 echo "Deploying..."
"""

REMOVED_SECRET_DIFF = """diff --git a/Sources/App/Config.swift b/Sources/App/Config.swift
index abc123..def456 100644
--- a/Sources/App/Config.swift
+++ b/Sources/App/Config.swift
@@ -1,3 +1,2 @@
 import Foundation
-let awsKey = "AKIAIOSFODNN7EXAMPLE"
 struct Config {}
"""


def test_clean_diff_returns_no_secrets():
    result = scan_diff_for_secrets(CLEAN_DIFF)
    assert result == [], f"Expected no secrets, got: {result}"


def test_aws_key_detected():
    result = scan_diff_for_secrets(AWS_KEY_DIFF)
    rule_names = [r.rule_name for r in result]
    assert "AWS Access Key ID" in rule_names


def test_github_pat_detected():
    result = scan_diff_for_secrets(GITHUB_PAT_DIFF)
    rule_names = [r.rule_name for r in result]
    assert "GitHub PAT" in rule_names


def test_removed_secret_not_flagged():
    """Secrets in removed lines (starting with '-') should NOT be flagged."""
    result = scan_diff_for_secrets(REMOVED_SECRET_DIFF)
    assert result == [], (
        "Removed lines should not be flagged — "
        "the secret is already gone in this PR."
    )


def test_secret_value_is_masked():
    result = scan_diff_for_secrets(AWS_KEY_DIFF)
    for occurrence in result:
        assert "AKIAIOSFODNN7EXAMPLE" not in occurrence.masked_value, (
            "Raw secret values must never appear in scanner output"
        )
        assert "****" in occurrence.masked_value


def test_line_numbers_are_positive():
    result = scan_diff_for_secrets(AWS_KEY_DIFF)
    for occurrence in result:
        assert occurrence.line_number > 0
