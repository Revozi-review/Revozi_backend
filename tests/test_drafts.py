"""Unit tests for the response draft generator."""
import pytest
from app.services.drafts import _fallback_drafts


class TestFallbackDrafts:
    def test_returns_three_drafts(self):
        drafts = _fallback_drafts()
        assert len(drafts) == 3

    def test_draft_tones(self):
        drafts = _fallback_drafts()
        tones = {d["tone"] for d in drafts}
        assert tones == {"short", "empathetic", "neutral"}

    def test_draft_content_not_empty(self):
        drafts = _fallback_drafts()
        for draft in drafts:
            assert len(draft["content"]) > 0

    def test_draft_structure(self):
        drafts = _fallback_drafts()
        for draft in drafts:
            assert "tone" in draft
            assert "content" in draft

    def test_no_fault_admission(self):
        drafts = _fallback_drafts()
        fault_words = ["sorry for our mistake", "we were wrong", "our fault", "we apologize for our error"]
        for draft in drafts:
            content_lower = draft["content"].lower()
            for word in fault_words:
                assert word not in content_lower, f"Draft contains fault admission: {word}"
