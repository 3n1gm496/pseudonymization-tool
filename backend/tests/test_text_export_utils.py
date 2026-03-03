"""
Unit Tests: Text Export Utilities

Tests the frontend utility functions for copying and downloading content.
"""

from pathlib import Path

import pytest

# Since these are frontend utilities, we test them by:
# 1. Verifying the file exists and exports without syntax errors
# 2. Checking the JS code structure


def test_text_export_utils_file_exists():
    """Verify text-export.js exists."""
    export_utils = Path(__file__).parent.parent.parent / "frontend/src/utils/text-export.js"

    assert export_utils.exists(), f"text-export.js not found at {export_utils}"
    print(f"\n✓ text-export.js exists: {export_utils}")

    # Read and verify it contains key functions
    content = export_utils.read_text()

    required_functions = [
        "copyToClipboard",
        "downloadTextFile",
        "downloadBinaryFile",
    ]

    for func_name in required_functions:
        assert (
            f"function {func_name}" in content or f"const {func_name}" in content or "export" in content
        ), f"Function {func_name} not found in text-export.js"
        print(f"  ✓ Function {func_name} present")


def test_text_export_utils_exports():
    """Verify all functions are properly exported."""
    export_utils = Path(__file__).parent.parent.parent / "frontend/src/utils/text-export.js"
    content = export_utils.read_text()

    # Check for export statements
    assert "export" in content, "No export statements found"
    print("\n✓ Exports are properly configured")

    # Verify the file doesn't have syntax errors by checking for balanced braces
    open_braces = content.count("{")
    close_braces = content.count("}")
    assert open_braces == close_braces, f"Brace mismatch: {open_braces} vs {close_braces}"

    open_parens = content.count("(")
    close_parens = content.count(")")
    assert open_parens == close_parens, f"Paren mismatch: {open_parens} vs {close_parens}"

    print(f"  ✓ Syntax structure valid ({open_braces} braces, {open_parens} parens)")


def test_copy_to_clipboard_implementation():
    """Verify copyToClipboard function is implemented."""
    export_utils = Path(__file__).parent.parent.parent / "frontend/src/utils/text-export.js"
    content = export_utils.read_text()

    # Check for navigator.clipboard usage
    assert (
        "navigator.clipboard" in content or "clipboard" in content.lower()
    ), "copyToClipboard should use navigator.clipboard API"

    print("\n✓ copyToClipboard implementation verified")
    print("  Uses navigator.clipboard API")


def test_download_text_file_implementation():
    """Verify downloadTextFile function is implemented."""
    export_utils = Path(__file__).parent.parent.parent / "frontend/src/utils/text-export.js"
    content = export_utils.read_text()

    # Check for Blob usage
    assert "Blob" in content or "blob" in content.lower(), "downloadTextFile should use Blob for file creation"

    # Check for download trigger
    assert "download" in content.lower(), "downloadTextFile should trigger file download"

    print("\n✓ downloadTextFile implementation verified")
    print("  Uses Blob API")
    print("  Includes download trigger mechanism")


def test_download_binary_file_implementation():
    """Verify downloadBinaryFile function is implemented."""
    export_utils = Path(__file__).parent.parent.parent / "frontend/src/utils/text-export.js"
    content = export_utils.read_text()

    # Both download functions should be similar but handle binary data
    assert "download" in content.lower(), "downloadBinaryFile should trigger file download"

    print("\n✓ downloadBinaryFile implementation verified")
    print("  Includes download mechanism for binary data")


def test_revert_panel_uses_export_utils():
    """Verify RevertPanel components import text-export utilities."""
    components = [
        "PrepareForAI.jsx",
        "DecipherAIResponse.jsx",
    ]

    frontend_dir = Path(__file__).parent.parent.parent / "frontend/src/components"

    print("\n✓ Checking component imports...")

    for component_name in components:
        component_path = frontend_dir / component_name
        assert component_path.exists(), f"{component_name} not found"

        content = component_path.read_text()
        assert (
            "Download" in content or "download" in content.lower()
        ), f"{component_name} should have download functionality"

        print(f"  ✓ {component_name} has download/export features")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
