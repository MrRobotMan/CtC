"""
Get the data on the latest cracking the cryptic video.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import smtplib
import ssl
import time
from datetime import timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, NamedTuple

import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ["YOUTUBE_KEY"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

BASE_URL = "https://youtube.googleapis.com/youtube/v3"

URL_PATTERN = re.compile(
    R"(https?):\/\/([\w_-]+(?:(?:\.[\w_-]+)+))([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-])"
)
# Pattern is
# 1st group: https? = http or https
# :\/\/ = :\\ (not captured)
# 2nd group: ([\w_-]+(?:(?:\.[\w_-]+)+)) =
#   [\w_-]+ => letters, numbers, _, - repeated
#   (?:(?:\.[\w_-]+)+)) => non-capturing group of non-capturing group of ., letters, numbers, _, - repeated
# 3rd group: ([\w.,@?^=%&:\/~+#-]*[\w@?^=%&\/~+#-]) => from / onward

TIME = re.compile(r"(?:PT)(?:(\d+)(?:H))?(?:(\d+)(?:M))?(?:(\d+)(?:S))?")
# Typical string comes in as PT<number>H<number>M<number>S with numbers at the underscores.
# If any are 0 that section is excluded, e.g 0:42:0 would be PT42M.
# Groups are set up to only capture the numbers.
# (:?(\d+)(?:<letter>))? => non-capture group of capture numbers and non-capture letter.


CTC_LATEST = Path("videos.json")


def mainloop():
    """
    Tool to get the latest Sudoku from CrackingTheCryptic
    """
    (channel, current) = initialize()
    current = Video.from_id(current)
    while True:
        try:
            last_video = get_latest_video(channel_id=channel)
            if (
                last_video.youtube_id != current.youtube_id
                and "crossword" not in last_video.title.lower()
                and "wordle" not in last_video.title.lower()
            ):
                atexit.unregister(write_out)
                current = last_video
                send_email(current.message())
                atexit.register(write_out, channel, current.youtube_id)
            time.sleep(600)
        except KeyboardInterrupt:
            return


class Video(NamedTuple):
    """
    Class to hold the useful data about a video
    """

    title: str
    sudoku_link: str
    duration: timedelta
    youtube_id: str

    def message(self) -> str:
        return (
            f"Video: {self.title} (https://www.youtube.com/watch?v={self.youtube_id})\n"
            f"Time: {self.pretty_time()}\n"
            f"Puzzle: {self.sudoku_link}"
        )

    def pretty_time(self) -> str:
        (hours, seconds_rem) = divmod(int(self.duration.total_seconds()), 3600)
        (minutes, seconds) = divmod(seconds_rem, 60)
        return f"{hours}:{minutes:02}:{seconds:02}"

    @classmethod
    def from_id(cls, video_id: str) -> Video:
        data = get_data(f"videos?part=snippet%2CcontentDetails&id={video_id}")
        run_time = get_time(data["contentDetails"]["duration"])
        description = data["snippet"]["description"]
        title = data["snippet"]["title"]

        urls = [
            link.group(0)
            for link in URL_PATTERN.finditer(description)
            if "tinyurl.com" in (lnk := link.group(0).lower())
            or "sudokupad.app" in lnk
            or "crackingthecryptic.com" in lnk
        ]
        if not urls:
            url = ""
        else:
            url = urls[0]
        return cls(title=title, sudoku_link=url, duration=run_time, youtube_id=video_id)


def get_latest_video(channel_id: str) -> Video:
    """
    Get the latest video published from the channel
    """

    channel = get_data(f"channels?part=contentDetails&id={channel_id}")

    playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    video = get_data(
        f"playlistItems?part=snippet%2CcontentDetails&maxResults=1&playlistId={playlist_id}"
    )

    latest_id = video["contentDetails"]["videoId"]

    return Video.from_id(latest_id)


def send_email(message: str):
    """
    Send an email with the latest video information.
    """
    msg = MIMEText(message)
    msg["Subject"] = "Cracking the Cryptic Video"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER

    context = ssl.create_default_context()
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls(context=context)
    server.login(EMAIL_USER, EMAIL_PASSWORD)
    server.send_message(msg)
    server.quit()


def get_data(payload: str) -> dict[str, Any]:
    """
    Gather the useful information from the JSON object as a dictionary.
    """
    return json.loads(
        requests.get(f"{BASE_URL}/{payload}&key={API_KEY}", timeout=5).text
    )["items"][0]


def get_time(runtime: str) -> timedelta:
    """
    Convert the runtime string into a struct_time
    """
    time_delta = timedelta(seconds=0)
    ma = TIME.match(runtime)
    if ma is None:
        return time_delta
    if (hours := ma.group(1)) is not None:
        time_delta += timedelta(hours=int(hours))
    if (minutes := ma.group(2)) is not None:
        time_delta += timedelta(minutes=int(minutes))
    if (seconds := ma.group(3)) is not None:
        time_delta += timedelta(seconds=int(seconds))
    return time_delta


def write_out(channel: str, video: str):
    """
    Write the last video to disk
    """
    with CTC_LATEST.open("w", encoding="utf8") as out:
        json.dump({"channel": channel, "last_id": video}, out, indent=2)


def initialize() -> tuple[str, str]:
    """
    Retrieve the last video found
    """
    with CTC_LATEST.open("r", encoding="utf8") as file:
        data = json.load(file)
    return data["channel"], data["last_id"]


if __name__ == "__main__":
    mainloop()
