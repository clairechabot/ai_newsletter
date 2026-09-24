from unittest.mock import patch, MagicMock
from briefing.voice import is_enabled, theme_steer, compose_greeting

ON = {"enabled": True, "name": "Sage", "tone": "warm"}

def test_is_enabled():
    assert is_enabled(ON)
    assert not is_enabled({})
    assert not is_enabled({"enabled": True})            # no name
    assert not is_enabled({"name": "Sage"})             # not enabled

def test_theme_steer_mentions_name_when_on():
    assert "Sage" in theme_steer(ON)
    assert theme_steer({}) == ""

def test_greeting_disabled_returns_empty():
    assert compose_greeting({}, [{"name": "T"}]) == ""

def test_greeting_no_themes_returns_empty():
    assert compose_greeting(ON, []) == ""

def _client(text):
    c = MagicMock(); block = MagicMock(); block.type = "text"; block.text = text
    msg = MagicMock(); msg.content = [block]; c.messages.create.return_value = msg
    return c

def test_greeting_returns_text_when_enabled():
    with patch("briefing.voice._client", return_value=_client("  Good morning.  ")):
        assert compose_greeting(ON, [{"name": "T"}]) == "Good morning."

def test_greeting_fails_soft_on_error():
    with patch("briefing.voice._client", side_effect=RuntimeError("no key")):
        assert compose_greeting(ON, [{"name": "T"}]) == ""

from briefing.voice import looks_like_reasoning, opening_habits

def test_reasoning_reply_is_discarded():
    with patch("briefing.voice._client", return_value=_client("Let me think... Good morning!")):
        assert compose_greeting(ON, [{"name": "T"}]) == ""

def test_reasoning_detector_leaves_normal_greetings():
    assert not looks_like_reasoning("Morning, friends: three stories worth your coffee.")
    assert looks_like_reasoning("Here's a greeting: hello")

def test_opening_habits_found():
    recent = ["Settle in, friends. A", "Settle in friends, B", "Something new today"]
    assert opening_habits(recent) == ["settle in friends"]

def test_recent_greetings_reach_the_prompt():
    c = _client("Fresh hello.")
    with patch("briefing.voice._client", return_value=c):
        compose_greeting(ON, [{"name": "T"}], recent=["Settle in now friends", "Settle in now all"])
    prompt = c.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Settle in now friends" in prompt
    assert '"settle in now"' in prompt

def test_mid_sentence_i_think_is_fine():
    assert not looks_like_reasoning("Good morning! I think you'll love today's picks.")
