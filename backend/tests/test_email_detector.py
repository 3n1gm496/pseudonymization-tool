"""
Unit tests for email detector.
"""
import pytest

from app.models.schemas import EntityType
from app.detectors.regex_detectors import EMAIL_DETECTOR
from app.parsers.base import TextChunk


class TestEmailDetector:
    """Test suite for EmailDetector."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test environment."""
        self.detector = EMAIL_DETECTOR

    def test_email_detection_simple(self):
        """Test detection of simple email addresses."""
        chunk = TextChunk(text="Contact: mario.rossi@example.com", source_ref="test-1")
        findings = self.detector.detect(chunk)

        assert len(findings) == 1
        assert findings[0].original_value == "mario.rossi@example.com"
        assert findings[0].entity_type == EntityType.EMAIL

    def test_email_detection_multiple(self):
        """Test detection of multiple emails in text."""
        chunk = TextChunk(
            text="Emails: user1@example.com, user2@test.org, admin@company.it",
            source_ref="test-2"
        )
        findings = self.detector.detect(chunk)

        assert len(findings) == 3
        detected_emails = [f.original_value for f in findings]
        assert "user1@example.com" in detected_emails
        assert "user2@test.org" in detected_emails
        assert "admin@company.it" in detected_emails

    def test_email_gov_domain(self):
        """Test detection of .gov.it emails."""
        chunk = TextChunk(text="Email: mario.rossi@ente.gov.it", source_ref="test-3")
        findings = self.detector.detect(chunk)

        assert len(findings) == 1
        assert findings[0].original_value == "mario.rossi@ente.gov.it"

    def test_email_false_positive_rejection(self):
        """Test that common false positives are rejected."""
        chunk = TextChunk(
            text="These are not emails: mario@, @example.com, mario.example.com",
            source_ref="test-4"
        )
        findings = self.detector.detect(chunk)

        assert len(findings) == 0

    def test_email_special_characters(self):
        """Test email with special characters."""
        chunk = TextChunk(text="Email: user+tag@example.org", source_ref="test-5")
        findings = self.detector.detect(chunk)

        assert len(findings) == 1
        assert findings[0].original_value == "user+tag@example.org"

    def test_no_email_in_text(self):
        """Test text without emails."""
        chunk = TextChunk(text="This is plain text without any email addresses.", source_ref="test-6")
        findings = self.detector.detect(chunk)

        assert len(findings) == 0

    @pytest.mark.parametrize("email", [
        "simple@example.org",
        "first.last@company.com",
        "user+filter@subdomain.example.com",
        "admin@test-domain.co.uk",
    ])
    def test_email_patterns(self, email):
        """Test various valid email patterns."""
        chunk = TextChunk(text=f"Email: {email}", source_ref="test-param")
        findings = self.detector.detect(chunk)

        assert len(findings) == 1
        assert findings[0].original_value == email
