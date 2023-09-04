from datetime import timedelta
from unittest import TestCase

import cracking_the_cryptic as ctc


class TestRunner(TestCase):
    def test_gathered_time_all(self):
        self.assertEqual(
            ctc.get_time("PT1H42M12S"), timedelta(hours=1, minutes=42, seconds=12)
        )

    def test_gathered_time_hours(self):
        self.assertEqual(ctc.get_time("PT1H"), timedelta(hours=1))

    def test_gathered_time_minutes(self):
        self.assertEqual(ctc.get_time("PT42M"), timedelta(minutes=42))

    def test_gathered_time_seconds(self):
        self.assertEqual(ctc.get_time("PT12S"), timedelta(seconds=12))

    def test_gathered_time_minutes_second(self):
        self.assertEqual(ctc.get_time("PT42M12S"), timedelta(minutes=42, seconds=12))

    def test_got_video(self):
        video_id = "39oIdXDf3J4"
        actual = ctc.Video.from_id(video_id)
        expected = ctc.Video(
            title="Sudoku, Gauss & Parity",
            sudoku_link="https://app.crackingthecryptic.com/sudoku/QR7MMGHpfJ",
            duration=timedelta(minutes=44, seconds=53),
            youtube_id=video_id,
        )
        self.assertEqual(actual, expected)
