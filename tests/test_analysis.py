"""Unit tests for the feedback analysis engine."""
import pytest
from app.services.analysis import _heuristic_analysis


class TestHeuristicAnalysis:
    def test_negative_feedback(self):
        result = _heuristic_analysis("The service was terrible and the staff was rude and awful")
        assert result["sentiment"] == "negative"
        assert result["risk_level"] in ("medium", "high")
        assert "service" in result["topics_detected"]

    def test_positive_feedback(self):
        result = _heuristic_analysis("Great experience! The staff was amazing and wonderful")
        assert result["sentiment"] == "positive"
        assert result["risk_level"] == "low"

    def test_neutral_feedback(self):
        result = _heuristic_analysis("I visited the store today and bought some items")
        assert result["sentiment"] == "neutral"
        assert result["risk_level"] == "low"

    def test_high_risk_detection(self):
        result = _heuristic_analysis("Terrible awful horrible worst experience ever, never again, disappointed and frustrated")
        assert result["sentiment"] == "negative"
        assert result["risk_level"] == "high"

    def test_topic_detection_pricing(self):
        result = _heuristic_analysis("The price was too expensive for what we got, not good value for money")
        assert "pricing" in result["topics_detected"]

    def test_topic_detection_delay(self):
        result = _heuristic_analysis("Had to wait forever, service was so slow and late delivery")
        assert "delay" in result["topics_detected"]

    def test_topic_detection_communication(self):
        result = _heuristic_analysis("Nobody would respond to my email or reply to my calls")
        assert "communication" in result["topics_detected"]

    def test_topic_detection_quality(self):
        result = _heuristic_analysis("The product quality was broken and defective")
        assert "quality" in result["topics_detected"]

    def test_output_structure(self):
        result = _heuristic_analysis("Some feedback text")
        assert "summary" in result
        assert "sentiment" in result
        assert "risk_level" in result
        assert "key_issues" in result
        assert "suggested_actions" in result
        assert "topics_detected" in result
        assert isinstance(result["key_issues"], list)
        assert isinstance(result["suggested_actions"], list)
        assert isinstance(result["topics_detected"], list)

    def test_sentiment_values(self):
        result = _heuristic_analysis("Some text")
        assert result["sentiment"] in ("positive", "neutral", "negative")

    def test_risk_level_values(self):
        result = _heuristic_analysis("Some text")
        assert result["risk_level"] in ("low", "medium", "high", "critical")
