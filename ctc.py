from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from utils import (
    LOGGER,
    send_email,
    write_out,
    contains_keyword,
    get_data,
    get_time,
    BadVideoError,
)

API_KEY = os.environ["YOUTUBE_KEY"]

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
IGNORES: list[str] = json.loads(Path("ignores.json").read_text(encoding="utf-8"))


async def ctc_mainloop(current: CtcCurrent) -> None:
    """Tool to get the latest Sudoku from CrackingTheCryptic."""
    LOGGER.debug("ctc_mainloop - Started CTC")
    while True:
        try:
            last_video = await get_latest_video(channel_id=current.channel)
        except BadVideoError:
            last_video = Video.empty()
        LOGGER.debug("ctc_mainloop - %s", last_video)
        if (
            (last_video.youtube_id != current.vid.youtube_id)
            and last_video.is_valid()
            and (last_video.published_time > current.vid.published_time)
        ):
            LOGGER.debug("ctc_mainloop - Updated CTC: %s -> %s", current, last_video)
            current.update(last_video)
            send_email(
                f"{current.vid.title} - {current.vid.pretty_time()}",
                current.vid.message(),
                "ctc",
            )
        await asyncio.sleep(60)


@dataclass
class CtcCurrent:
    vid: Video
    channel: str

    def update(self, vid: Video) -> None:
        LOGGER.debug("Updating %s with category %s", self, vid)
        self.vid = vid
        write_out({"channel": self.channel, "last_id": vid.youtube_id}, CTC_LATEST)


class Video(NamedTuple):
    """Class to hold the useful data about a video."""

    title: str
    sudoku_links: list[str]
    duration: timedelta
    youtube_id: str
    published_time: datetime

    def message(self) -> str:
        links = "\n".join(lnk for lnk in self.sudoku_links)
        return (
            f"Video title: {self.title}\n"
            f"Video link: https://www.youtube.com/watch?v={self.youtube_id}\n"
            f"Time: {self.pretty_time()}\n"
            f"Puzzle: {links}"
        )

    def pretty_time(self) -> str:
        (hours, seconds_rem) = divmod(int(self.duration.total_seconds()), 3600)
        (minutes, seconds) = divmod(seconds_rem, 60)
        return f"{hours}:{minutes:02}:{seconds:02}"

    def is_valid(self) -> bool:
        return not contains_keyword(
            self.title.lower(), IGNORES
        ) and self.duration > timedelta(seconds=0)

    @classmethod
    async def from_id(cls, video_id: str) -> Video:
        data = await get_data(
            f"{BASE_URL}/videos?part=snippet%2CcontentDetails&id={video_id}&key={API_KEY}"
        )
        run_time = get_time(data["contentDetails"]["duration"], TIME)
        published_time = datetime.strptime(
            data["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ"
        )
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
            title=title,
            sudoku_links=urls,
            duration=run_time,
            youtube_id=video_id,
            published_time=published_time,
        )

    @classmethod
    def empty(cls) -> Video:
        return Video(
            title="",
            sudoku_links=[],
            duration=timedelta(0),
            youtube_id="",
            published_time=datetime(
                year=1900, month=1, day=1, hour=0, minute=0, second=0
            ),
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
