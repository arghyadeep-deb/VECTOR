"""Regression: SentimentAnalyzer.analyze()'s docstring promises a 3-tier
"keyword -> embedding -> LLM fallback" cascade (core/config.py's own
sentiment_method: str comment lists the 3 valid values: keyword | embedding
| llm), but the gating condition for attempting the embedding tier only
matched self._method == "embedding" -- never "llm". Configuring
sentiment_method="llm" (the full documented cascade) silently skipped the
embedding tier entirely, going straight from keyword to llm on low keyword
confidence. core/personality/sentiment.py, Phase 3 whole-repo audit
(2026-10-02).
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.personality.sentiment import SentimentAnalyzer, SentimentResult


def _low_confidence_keyword_result():
    return SentimentResult(emotion="neutral", intensity=0.0, urgency=0.0, confidence=0.0, raw_scores={})


def test_llm_method_attempts_embedding_tier_before_llm():
    analyzer = SentimentAnalyzer()
    analyzer._method = "llm"
    with patch.object(analyzer, "_keyword_analyze", return_value=_low_confidence_keyword_result()), \
         patch.object(analyzer, "_embedding_analyze") as mock_embed, \
         patch.object(analyzer, "_llm_analyze", return_value=_low_confidence_keyword_result()):
        mock_embed.return_value = _low_confidence_keyword_result()
        analyzer.analyze("some text")
    mock_embed.assert_called_once()


def test_embedding_method_still_attempts_embedding_tier():
    analyzer = SentimentAnalyzer()
    analyzer._method = "embedding"
    with patch.object(analyzer, "_keyword_analyze", return_value=_low_confidence_keyword_result()), \
         patch.object(analyzer, "_embedding_analyze") as mock_embed:
        mock_embed.return_value = _low_confidence_keyword_result()
        analyzer.analyze("some text")
    mock_embed.assert_called_once()


def test_keyword_method_does_not_attempt_embedding_tier():
    analyzer = SentimentAnalyzer()
    analyzer._method = "keyword"
    with patch.object(analyzer, "_keyword_analyze", return_value=_low_confidence_keyword_result()), \
         patch.object(analyzer, "_embedding_analyze") as mock_embed:
        analyzer.analyze("some text")
    mock_embed.assert_not_called()


def test_high_confidence_keyword_result_short_circuits_everything():
    analyzer = SentimentAnalyzer()
    analyzer._method = "llm"
    high_conf = SentimentResult(emotion="happy", intensity=0.9, urgency=0.0, confidence=0.9, raw_scores={})
    with patch.object(analyzer, "_keyword_analyze", return_value=high_conf), \
         patch.object(analyzer, "_embedding_analyze") as mock_embed, \
         patch.object(analyzer, "_llm_analyze") as mock_llm:
        result = analyzer.analyze("great job")
    mock_embed.assert_not_called()
    mock_llm.assert_not_called()
    assert result.emotion == "happy"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
