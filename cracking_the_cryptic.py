"""
Get the data on the latest cracking the cryptic video.
"""

from __future__ import annotations

import json
import os
import re
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any, NamedTuple
import asyncio
from dataclasses import dataclass
from html.parser import HTMLParser

import requests
import dotenv

import logging

handler = logging.FileHandler("ctc.log", encoding="utf8")
handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.ERROR)
LOGGER.addHandler(handler)


dotenv.load_dotenv()
API_KEY = os.environ["YOUTUBE_KEY"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
PHONE = os.environ["PHONE"]
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465

BASE_URL = "https://youtube.googleapis.com/youtube/v3"
SANDRA_AND_NALA = "https://logic-masters.de/Raetselportal/Suche/erweitert.php?suchautor=SandraNala&suchverhalt=nichtgeloest"
DAY = 60 * 60 * 24

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
SANDRA_AND_NALA_LATEST = Path("lmd.json")


async def mainloop():
    """
    Tool to get the latest Sudoku from CrackingTheCryptic and Sandra&Nala
    """
    data = await read_data(CTC_LATEST)
    channel = data["channel"]
    channel = channel if isinstance(channel, str) else ""
    video_id = data["last_id"]
    video_id = video_id if isinstance(video_id, str) else ""
    ctc_video = await Video.from_id(video_id)
    sandra_and_nala = Link()
    current = Current(ctc_video, channel, sandra_and_nala)
    ctc = asyncio.create_task(ctc_mainloop(current, channel))
    lmd = asyncio.create_task(sandra_and_nala_mainloop(current))
    await ctc
    await lmd


async def ctc_mainloop(current: Current, channel: str):
    """
    Tool to get the latest Sudoku from CrackingTheCryptic
    """
    while True:
        last_video = await get_latest_video(channel_id=channel)
        if last_video.youtube_id != current.ctc.youtube_id and last_video.is_valid():
            await current.update(last_video)
            LOGGER.info("CTC: %s", last_video)
            await send_email(None, current.ctc.message(), PHONE)
        await asyncio.sleep(60)


async def sandra_and_nala_mainloop(current: Current):
    """
    Tool to get the latest Sudoku from Sandra & Nala
    """
    while True:
        response = requests.get(SANDRA_AND_NALA)
        if response.ok:
            latest = await get_latest(response.text)
            data = await read_data(SANDRA_AND_NALA_LATEST)
            from_disk = Link.from_file(data["sandra and nala"])
            if latest != from_disk:
                await current.update(latest)
                LOGGER.info("LMD: %s", latest)
                await send_email(
                    f"New Sandra and Nala Sudoku: {current.sandra_and_nala.title}",
                    f"Try Sandra & Nala's puzzle {current.sandra_and_nala.title}, https://logic-masters.de{current.sandra_and_nala.url}",
                    EMAIL_USER,
                )
        await asyncio.sleep(DAY)


@dataclass
class Current:
    ctc: Video
    channel: str
    sandra_and_nala: Link

    async def update(self, vid: Video | Link):
        match vid:
            case Video():
                self.ctc = vid
                await write_out({"channel": self.channel, "last_id": vid.youtube_id}, CTC_LATEST)
            case Link():
                self.sandra_and_nala = vid
                await write_out({"sandra and nala": vid.to_json()}, SANDRA_AND_NALA_LATEST)


class Video(NamedTuple):
    """
    Class to hold the useful data about a video
    """

    title: str
    sudoku_links: list[str]
    duration: timedelta
    youtube_id: str

    def message(self) -> str:
        links = "\n".join(l for l in self.sudoku_links)
        return (
            f"Video: {self.title} (https://www.youtube.com/watch?v={self.youtube_id})\n"
            f"Time: {self.pretty_time()}\n"
            f"Puzzle: {links}"
        )

    def pretty_time(self) -> str:
        (hours, seconds_rem) = divmod(int(self.duration.total_seconds()), 3600)
        (minutes, seconds) = divmod(seconds_rem, 60)
        return f"{hours}:{minutes:02}:{seconds:02}"

    def is_valid(self) -> bool:
        title = self.title.lower()
        return (
            "crossword" not in title
            and "wordle" not in title
            and "sudoku experts play" not in title
            and self.duration > timedelta(seconds=0)
        )

    @classmethod
    async def from_id(cls, video_id: str) -> Video:
        data = await get_data(f"videos?part=snippet%2CcontentDetails&id={video_id}")
        run_time = await get_time(data["contentDetails"]["duration"])
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
            urls = [""]
        for lnk in ("https://tinyurl.com/CTCCatalogue", "https://crackingthecryptic.com/#apps"):
            if lnk in urls:
                urls.remove(lnk)
        return cls(title=title, sudoku_links=urls, duration=run_time, youtube_id=video_id)


async def get_latest_video(channel_id: str) -> Video:
    """
    Get the latest video published from the channel
    """

    channel = await get_data(f"channels?part=contentDetails&id={channel_id}")

    playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    video = await get_data(
        f"playlistItems?part=snippet%2CcontentDetails&maxResults=1&playlistId={playlist_id}"
    )

    latest_id = video["contentDetails"]["videoId"]

    return await Video.from_id(latest_id)


async def send_email(subject: str | None, message: str, receiver: str):
    """
    Send an email with the latest video information.
    """
    msg = EmailMessage()
    if subject:
        msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = receiver
    msg.set_content(message)

    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.login(EMAIL_USER, EMAIL_PASSWORD)
        smtp.send_message(msg)
        LOGGER.info(f"sent {msg}")


async def get_data(payload: str) -> dict[str, Any]:
    """
    Gather the useful information from the JSON object as a dictionary.
    """
    return json.loads(requests.get(f"{BASE_URL}/{payload}&key={API_KEY}", timeout=5).text)["items"][
        0
    ]


async def get_time(runtime: str) -> timedelta:
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


async def write_out(data: Any, file: Path):
    """
    Write the last video to disk
    """
    with file.open("w", encoding="utf8") as out:
        json.dump(data, out, indent=2)


async def read_data(file: Path) -> dict[str, str | dict[str, str]]:
    """
    Read stored data.
    """
    with file.open("r", encoding="utf8") as fp:
        return json.load(fp)


class LogicMastersParser(HTMLParser):
    def __init__(self):
        self.links: list[Link] = []
        self.table_found: bool = False
        self.current: Link = Link()
        super().__init__()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag == "table":
            self.table_found = True

        if self.table_found and tag == "a":
            for attr in attrs:
                if attr[1]:
                    self.current.url = attr[1]

    def handle_endtag(self, tag: str):
        if self.table_found and tag == "a":
            self.links.append(self.current)
            self.current = Link()

    def handle_data(self, data: str):
        if self.table_found:
            self.current.title = data

    def __str__(self):
        return str(self.links[0])


@dataclass
class Link:
    url: str = ""
    title: str = ""

    @staticmethod
    def from_file(data: str | dict[str, str]) -> Link:
        if isinstance(data, str):
            url, title = data.split(" ")
        else:
            url = data["url"]
            title = data["title"]
        return Link(url, title)

    def to_json(self) -> dict[str, str]:
        return {"url": self.url, "title": self.title}


async def get_latest(html: str) -> Link:
    parser = LogicMastersParser()
    parser.feed(html)
    return parser.links[0]


if __name__ == "__main__":
    asyncio.run(mainloop())
