from core.voice.voice_personality import VoicePersonality


def test_remove_fillers():
    vp = VoicePersonality()
    result = vp.remove_fillers("So um, like, you know we need to check")
    assert "um" not in result
    assert "like" not in result
    assert "you know" not in result
    assert "we need to check" in result


def test_remove_fillers_no_fillers():
    vp = VoicePersonality()
    text = "Hello, how are you?"
    assert vp.remove_fillers(text) == text


def test_remove_fillers_empty():
    vp = VoicePersonality()
    assert vp.remove_fillers("") == ""


def test_add_pauses_dramatic():
    vp = VoicePersonality()
    text = "Hello. How are you?"
    result = vp.add_pauses(text, {"pause_style": "dramatic"})
    assert "..." in result


def test_add_pauses_conversational():
    vp = VoicePersonality()
    text = "Hello. How are you?"
    result = vp.add_pauses(text, {"pause_style": "conversational"})
    assert ".." in result


def test_add_pauses_no_config():
    vp = VoicePersonality()
    text = "Hello. How are you?"
    result = vp.add_pauses(text)
    assert result == text


def test_get_speech_rate_neutral():
    vp = VoicePersonality()
    assert vp.get_speech_rate("neutral") == 160


def test_get_speech_rate_with_speed():
    vp = VoicePersonality()
    assert vp.get_speech_rate("neutral", {"speed": 200}) == 200


def test_get_speech_rate_urgent():
    vp = VoicePersonality()
    assert vp.get_speech_rate("urgent") == 190


def test_modulate():
    vp = VoicePersonality()
    result = vp.modulate("Hello um world", "neutral")
    assert "um" not in result
