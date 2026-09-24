from briefing.editions import pick_edition, edition_filename

EDITIONS = [
    {"key": "morning", "label": "Morning Edition", "until_hour": 12},
    {"key": "evening", "label": "Evening Edition"},
]

def test_no_editions_returns_daily():
    slot = pick_edition([], 9)
    assert slot["key"] == "daily"
    assert slot["label"] == ""

def test_morning_before_boundary():
    assert pick_edition(EDITIONS, 7)["key"] == "morning"
    assert pick_edition(EDITIONS, 11)["key"] == "morning"

def test_evening_is_catch_all_after_boundary():
    assert pick_edition(EDITIONS, 12)["key"] == "evening"
    assert pick_edition(EDITIONS, 18)["key"] == "evening"
    assert pick_edition(EDITIONS, 23)["label"] == "Evening Edition"

def test_edition_filename():
    assert edition_filename("2026-06-29", "morning") == "2026-06-29-morning.html"
