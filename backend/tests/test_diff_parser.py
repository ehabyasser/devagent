"""
tests/test_diff_parser.py

Unit tests for the diff parser.
"""
import pytest
from backend.tools.diff_parser import parse_diff


VALID_DIFF = """diff --git a/Sources/App/ViewModel.swift b/Sources/App/ViewModel.swift
index abc123..def456 100644
--- a/Sources/App/ViewModel.swift
+++ b/Sources/App/ViewModel.swift
@@ -1,10 +1,15 @@
 import Foundation
 import Combine
+import SwiftUI

 @MainActor
 class ViewModel: ObservableObject {
     @Published var items: [Item] = []
+    @Published var isLoading: Bool = false
+    @Published var errorMessage: String?

     func fetchItems() async {
+        isLoading = true
+        defer { isLoading = false }
         // TODO: fetch from API
     }
 }
diff --git a/Sources/App/Item.swift b/Sources/App/Item.swift
new file mode 100644
index 0000000..abc123
--- /dev/null
+++ b/Sources/App/Item.swift
@@ -0,0 +1,8 @@
+import Foundation
+
+struct Item: Identifiable, Codable, Sendable {
+    let id: UUID
+    let title: String
+    let createdAt: Date
+    var isCompleted: Bool
+}
"""


def test_parse_valid_diff():
    result = parse_diff(VALID_DIFF)
    assert result.files_changed == 2
    assert result.lines_added > 0
    assert result.diff_hash != ""


def test_parse_empty_diff_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_diff("")


def test_parse_whitespace_only_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_diff("   \n  ")


def test_diff_hash_is_sha256():
    result = parse_diff(VALID_DIFF)
    assert len(result.diff_hash) == 64  # SHA-256 hex digest


def test_same_diff_same_hash():
    r1 = parse_diff(VALID_DIFF)
    r2 = parse_diff(VALID_DIFF)
    assert r1.diff_hash == r2.diff_hash


def test_truncation_respects_limit():
    # Create a large diff by repeating the valid one
    large_diff = VALID_DIFF * 200
    result = parse_diff(large_diff)
    assert len(result.truncated_diff) <= 8_500  # 8 KB + a bit for truncation notice


def test_file_summaries_have_expected_keys():
    result = parse_diff(VALID_DIFF)
    for summary in result.file_summaries:
        assert "path" in summary
        assert "added" in summary
        assert "removed" in summary
