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
                "crossword" not in last_video.title.lower()
                and "wordle" not in last_video.title.lower()
                and last_video.youtube_id != current.youtube_id
            ):
                atexit.unregister(write_out)
                current = last_video
                send_email(current.message())
                atexit.register(write_out, channel, current.youtube_id)
        except KeyboardInterrupt:
            return


class Video(NamedTuple):
    """
    Class to hold the useful data about a video
    """

    title: str
    sudoku_link: str
    duration: time.struct_time
    youtube_id: str

    def message(self) -> str:
        return (
            f"The latest video {self.title} (https://www.youtube.com/watch?v={self.youtube_id}) "
            f"for {self.sudoku_link}) took {time.strftime('%H:%M:%S', self.duration)}"
        )

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

    # data = get_data(f"videos?part=snippet%2CcontentDetails&id={latest_id}")
    # run_time = get_time(data["contentDetails"]["duration"])
    # description = data["snippet"]["description"]
    # title = data["snippet"]["title"]

    # urls = [
    #     link.group(0)
    #     for link in URL_PATTERN.finditer(description)
    #     if "tinyurl.com" in (lnk := link.group(0).lower())
    #     or "sudokupad.app" in lnk
    #     or "crackingthecryptic.com" in lnk
    # ]
    # if not urls:
    #     url = ""
    # else:
    #     url = urls[0]
    # return Video(title=title, sudoku_link=url, duration=run_time, youtube_id=latest_id)


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


def get_time(runtime: str) -> time.struct_time:
    """
    Convert the runtime string into a struct_time
    """
    try:
        return time.strptime(runtime, "PT%HH%MM%SS")
    except ValueError:
        try:
            return time.strptime(runtime, "PT%MM%SS")
        except ValueError:
            return time.strptime(runtime, "PT%SS")


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
