from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st

import cracking_the_cryptic as ctc


def test_gathered_time_all():
    assert ctc.get_time("PT1H42M12S") == timedelta(hours=1, minutes=42, seconds=12)


def test_gathered_time_hours():
    assert ctc.get_time("PT1H") == timedelta(hours=1)


def test_gathered_time_minutes():
    assert ctc.get_time("PT42M") == timedelta(minutes=42)


def test_gathered_time_seconds():
    assert ctc.get_time("PT12S") == timedelta(seconds=12)


def test_gathered_time_minutes_second():
    assert ctc.get_time("PT42M12S") == timedelta(minutes=42, seconds=12)


def test_bad_string():
    assert ctc.get_time("") == timedelta(seconds=0)


@given(
    st.integers(min_value=0, max_value=24),
    st.integers(min_value=0, max_value=60),
    st.integers(min_value=0, max_value=60),
)
def test_rand(hours: int, minutes: int, seconds: int):
    time_code = "PT"
    if hours > 0:
        time_code += f"{hours}H"
    if minutes > 0:
        time_code += f"{minutes}M"
    if seconds > 0:
        time_code += f"{seconds}S"
    assert ctc.get_time(time_code) == timedelta(
        hours=hours, minutes=minutes, seconds=seconds
    )


def test_got_video():
    video_id = "39oIdXDf3J4"
    actual = ctc.Video.from_id(video_id)
    assert actual.pretty_time() == "0:44:53"
    expected = ctc.Video(
        title="Sudoku, Gauss & Parity",
        sudoku_link="https://app.crackingthecryptic.com/sudoku/QR7MMGHpfJ",
        duration=timedelta(minutes=44, seconds=53),
        youtube_id=video_id,
    )
    assert actual == expected
