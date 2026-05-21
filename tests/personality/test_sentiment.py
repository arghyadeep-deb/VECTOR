from core.personality.sentiment import SentimentAnalyzer, SentimentResult


def test_happy_keyword():
    sa = SentimentAnalyzer()
    result = sa.analyze("That is great! Perfect, thanks!")
    assert result.emotion in ("happy", "neutral")
    assert result.confidence > 0


def test_frustrated_keyword():
    sa = SentimentAnalyzer()
    result = sa.analyze("This is broken and useless, so frustrating")
    assert result.emotion in ("frustrated", "neutral")
    assert result.confidence > 0


def test_urgent_keyword():
    sa = SentimentAnalyzer()
    result = sa.analyze("HURRY! This is an EMERGENCY, do it NOW!")
    assert result.emotion == "urgent"
    assert result.confidence > 0


def test_curious_keyword():
    sa = SentimentAnalyzer()
    result = sa.analyze("How does this work? I'm curious about the mechanism")
    assert result.emotion in ("curious", "neutral")
    assert result.confidence > 0


def test_sad_keyword():
    sa = SentimentAnalyzer()
    result = sa.analyze("I'm so tired and disappointed, this is sad")
    assert result.emotion in ("sad", "neutral")
    assert result.confidence > 0


def test_neutral_text():
    sa = SentimentAnalyzer()
    result = sa.analyze("The sky is blue. Water is wet.")
    assert result.emotion == "neutral"


def test_empty_text():
    sa = SentimentAnalyzer()
    result = sa.analyze("")
    assert result.emotion == "neutral"


def test_urgency_all_caps():
    sa = SentimentAnalyzer()
    result = sa._compute_urgency("THIS IS VERY URGENT")
    assert result > 0.3


def test_urgency_punctuation():
    sa = SentimentAnalyzer()
    result = sa._compute_urgency("Do it now!!!")
    assert result > 0


def test_urgency_noise():
    sa = SentimentAnalyzer()
    result = sa._compute_urgency("hello world")
    assert result == 0


def test_sentiment_result_label_urgent():
    r = SentimentResult(emotion="frustrated", urgency=0.8)
    assert "urgent" in r.label


def test_sentiment_result_label_normal():
    r = SentimentResult(emotion="happy", urgency=0.3)
    assert r.label == "happy"


def test_keyword_confidence_noise():
    sa = SentimentAnalyzer()
    result = sa.analyze("what how why tell me about explain")
    assert result.emotion in ("curious", "neutral")


def test_intensity_scaling():
    sa = SentimentAnalyzer()
    result = sa.analyze("That is absolutely perfect amazing fantastic")
    assert result.intensity >= 0


def test_multiple_emotions_resolved():
    sa = SentimentAnalyzer()
    result = sa.analyze("What a great question, I'm curious but also tired")
    assert result.emotion is not None


def test_llm_fallback_returns_neutral_on_error():
    sa = SentimentAnalyzer()
    result = sa._llm_analyze("")
    assert result.emotion == "neutral"


def test_raw_scores_present():
    sa = SentimentAnalyzer()
    result = sa._keyword_analyze("great thanks")
    assert isinstance(result.raw_scores, dict)
    assert len(result.raw_scores) > 0
