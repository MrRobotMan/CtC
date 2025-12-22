"""Get the data on the latest cracking the cryptic video."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from email.message import EmailMessage
from enum import Enum, auto
from html.parser import HTMLParser
import json
import logging
import os
from pathlib import Path
import re
import smtplib
from typing import Any, NamedTuple

import dotenv
import httpx

error_handler = logging.FileHandler("ctc.log", encoding="utf8")
error_handler.setLevel(logging.ERROR)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
error_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
LOGGER.addHandler(error_handler)
LOGGER.addHandler(stream_handler)


dotenv.load_dotenv()
API_KEY = os.environ["YOUTUBE_KEY"]
SMTP_SERVER = os.environ["SMTP_SERVER"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
PHONE = os.environ["PHONE"]
EMAIL_RECIPIENT = os.environ["EMAIL_RECIPIENT"]
SMTP_PORT = 587

BASE_URL = "https://youtube.googleapis.com/youtube/v3"
SANDRA_AND_NALA = "https://logic-masters.de/Raetselportal/Suche/erweitert.php?suchautor=SandraNala&suchverhalt=nichtgeloest"
RAT_RUN = "https://logic-masters.de/Raetselportal/Suche/erweitert.php?skname=x&suchtext=rat%20run&suchautor=marty_sears"
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
LMD_LATEST = Path("lmd.json")
OK_RESPONSE = 200


async def mainloop() -> None:
    """Tool to get the latest Sudoku from CrackingTheCryptic and Sandra&Nala."""
    data = read_data(CTC_LATEST)
    channel = data["channel"]
    channel = channel if isinstance(channel, str) else ""
    video_id = data["last_id"]
    video_id = video_id if isinstance(video_id, str) else ""
    try:
        ctc_video = await Video.from_id(video_id)
    except BadVideoError:
        ctc_video = Video("", [], timedelta(), "")
    lmd = read_data(LMD_LATEST)
    sandra_and_nala = Link.from_file(lmd.get("sandra and nala"))
    rat_run = Link.from_file(lmd.get("rat run"))
    current = Current(ctc_video, channel, sandra_and_nala, rat_run)
    ctc = asyncio.create_task(ctc_mainloop(current, channel))
    lmd = asyncio.create_task(lmd_mainloop(current))
    await ctc
    await lmd


async def ctc_mainloop(current: Current, channel: str) -> None:
    """Tool to get the latest Sudoku from CrackingTheCryptic."""
    while True:
        try:
            last_video = await get_latest_video(channel_id=channel)
        except BadVideoError:
            pass
        else:
            if (
                last_video.youtube_id != current.ctc.youtube_id
                and last_video.is_valid()
            ):
                await current.update(last_video, LogicMasters.NONE)
                LOGGER.info("CTC: %s", last_video)
                send_email(current.ctc.title, current.ctc.message(), EMAIL_RECIPIENT)
        finally:
            await asyncio.sleep(60)


async def lmd_mainloop(current: Current) -> None:
    """Tool to get the latest Sudoku from Sandra & Nala."""
    while True:
        async with httpx.AsyncClient() as client:
            responses = (
                (
                    await client.get(SANDRA_AND_NALA, timeout=60),
                    LogicMasters.SANDRAANDNALA,
                ),
                (await client.get(RAT_RUN, timeout=60), LogicMasters.RATRUN),
            )
        for response in responses:
            await process_response(current, *response)
        await asyncio.sleep(DAY)


async def process_response(
    current: Current, response: httpx.Response, lmd: LogicMasters
) -> None:
    if response.status_code == OK_RESPONSE:
        latest = get_latest(response.text)
        LOGGER.info(latest)
        data = read_data(LMD_LATEST)
        from_disk = Link.from_file(data.get(lmd.to_string()))
        LOGGER.info(from_disk)
        if latest != from_disk:
            string = lmd.to_string().title()
            await current.update(latest, lmd)
            LOGGER.info("LMD: %s", latest)
            send_email(
                f"New {string} Sudoku: {latest.title}",
                f"Try the new {string} puzzle {latest.title}, https://logic-masters.de{latest.url}",
                EMAIL_RECIPIENT,
            )


@dataclass
class Current:
    ctc: Video
    channel: str
    sandra_and_nala: Link
    rat_run: Link

    async def update(self, item: Video | Link, lmd: LogicMasters) -> None:
        match item:
            case Video():
                self.ctc = item
                write_out(
                    {"channel": self.channel, "last_id": item.youtube_id}, CTC_LATEST
                )
            case Link():
                match lmd:
                    case LogicMasters.SANDRAANDNALA:
                        self.sandra_and_nala = item
                    case LogicMasters.RATRUN:
                        self.rat_run = item
                    case LogicMasters.NONE:
                        pass
                write_out(
                    {
                        "sandra and nala": self.sandra_and_nala.to_json(),
                        "rat run": self.rat_run.to_json(),
                    },
                    LMD_LATEST,
                )


class Video(NamedTuple):
    """Class to hold the useful data about a video."""

    title: str
    sudoku_links: list[str]
    duration: timedelta
    youtube_id: str

    def message(self) -> str:
        links = "\n".join(lnk for lnk in self.sudoku_links)
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
            urls = [""]
        for lnk in (
            "https://tinyurl.com/CTCCatalogue",
            "https://crackingthecryptic.com/#apps",
        ):
            if lnk in urls:
                urls.remove(lnk)
        return cls(
            title=title, sudoku_links=urls, duration=run_time, youtube_id=video_id
        )


async def get_latest_video(channel_id: str) -> Video:
    """
    Get the latest video published from the channel.

    Returns
    -------
    Video: Information of the found youtube link.

    """
    channel = await get_data(f"channels?part=contentDetails&id={channel_id}")
    playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    video = await get_data(
        f"playlistItems?part=snippet%2CcontentDetails&maxResults=1&playlistId={playlist_id}"
    )

    latest_id = video["contentDetails"]["videoId"]

    return await Video.from_id(latest_id)


def send_email(subject: str | None, message: str, receiver: str) -> None:
    """Send an email with the latest video information."""
    msg = EmailMessage()
    if subject:
        msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = receiver
    msg.set_content(message)

    smtp = smtplib.SMTP(SMTP_SERVER, 587)
    smtp.ehlo()
    smtp.starttls()
    smtp.login(EMAIL_USER, EMAIL_PASSWORD)
    smtp.send_message(msg)
    message = f"sent {msg}"
    LOGGER.info(message)


async def get_data(payload: str) -> dict[str, Any]:
    """
    Gather the useful information from the JSON object as a dictionary.

    Returns
    -------
    JSON data for the information.

    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/{payload}&key={API_KEY}", timeout=5)
    try:
        return json.loads(response.text)["items"][0]
    except IndexError:
        raise BadVideoError


def get_time(runtime: str) -> timedelta:
    """
    Convert the runtime string into a struct_time.

    Returns
    -------
    Video runtime.

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


def write_out(data: dict[str, str | dict[str, str]], file: Path) -> None:
    """Write the last video to disk."""
    with file.open("w", encoding="utf8") as out:
        json.dump(data, out, indent=2)


def read_data(file: Path) -> dict[str, str | dict[str, str]]:
    """
    Read stored data.

    Returns
    -------
    Current file information.

    """
    with file.open("r", encoding="utf8") as fp:
        return json.load(fp)


class LogicMastersParser(HTMLParser):
    def __init__(self):
        self.links: list[Link] = []
        self.table_found: bool = False
        self.current: Link = Link()
        super().__init__()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.table_found = True

        if self.table_found and tag == "a":
            for attr in attrs:
                if attr[1]:
                    self.current.url = attr[1]

    def handle_endtag(self, tag: str) -> None:
        if self.table_found and tag == "a":
            self.links.append(self.current)
            self.current = Link()

    def handle_data(self, data: str) -> None:
        if self.table_found:
            self.current.title = data

    def __str__(self):
        return str(self.links[0])


class LogicMasters(Enum):
    NONE = auto()
    SANDRAANDNALA = auto()
    RATRUN = auto()

    def to_string(self) -> str:
        match self:
            case LogicMasters.NONE:
                return ""
            case LogicMasters.SANDRAANDNALA:
                return "sandra and nala"
            case LogicMasters.RATRUN:
                return "rat run"


@dataclass
class Link:
    url: str = ""
    title: str = ""

    @staticmethod
    def from_file(data: str | dict[str, str] | None) -> Link:
        match data:
            case str():
                url, title = data.split(" ")
            case None:
                url, title = "", ""
            case _:
                url = data["url"]
                title = data["title"]
        return Link(url, title)

    def to_json(self) -> dict[str, str]:
        return {"url": self.url, "title": self.title}


def get_latest(html: str) -> Link:
    parser = LogicMastersParser()
    parser.feed(html)
    return parser.links[0]


class BadVideoError(Exception):
    pass


if __name__ == "__main__":
    asyncio.run(mainloop())
