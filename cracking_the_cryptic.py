"""
Get the data on the latest cracking the cryptic video.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, NamedTuple

import requests

with open(".env", encoding="utf8") as dotenv:
    API_KEY = dotenv.readline().strip().split("=")[1]
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


async def main() -> Video | None:
    """
    Tool to get the latest Sudoku from CrackingTheCryptic
    """
    with CTC_LATEST.open("r", encoding="utf8") as file:
        channel_id = json.load(file)["Channel"]
    last_video = await get_latest_video(channel_id=channel_id)
    current_id = await get_lastest()
    if (
        "crossword" in last_video.title.lower()
        or "wordle" in last_video.title.lower()
        or last_video.youtube_id == current_id
    ):
        return
    await write_out(channel_id, last_video.youtube_id)
    return last_video


class Video(NamedTuple):
    """
    Class to hold the useful data about a video
    """

    title: str
    sudoku_link: str
    duration: time.struct_time
    youtube_id: str


async def get_latest_video(channel_id: str) -> Video:
    """
    Get the latest video published from the channel
    """

    channel = get_data(f"channels?part=contentDetails&id={channel_id}")

    playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]

    video = get_data(
        f"playlistItems?part=snippet%2CcontentDetails&maxResults=1&playlistId={playlist_id}"
    )

    latest_id = video["contentDetails"]["videoId"]

    data = get_data(f"videos?part=snippet%2CcontentDetails&id={latest_id}")
    run_time = get_time(data["contentDetails"]["duration"])
    description = data["snippet"]["description"]
    title = data["snippet"]["title"]

    urls = [
        link.group(0)
        for link in URL_PATTERN.finditer(description)
        if "tinyurl.com" in link.group(0).lower()
        or "sudokupad.app" in link.group(0).lower()
    ]
    if not urls:
        url = ""
    else:
        url = urls[0]
    return Video(title=title, sudoku_link=url, duration=run_time, youtube_id=latest_id)


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


async def write_out(channel: str, video: str):
    """
    Write the last video to disk
    """
    with CTC_LATEST.open("w", encoding="utf8") as out:
        json.dump({"Channel": channel, "LastID": video}, out)


async def get_lastest() -> str:
    """
    Retrieve the last video found
    """
    with CTC_LATEST.open("r", encoding="utf8") as file:
        return json.load(file)["LastID"]


def initialize():
    """Create any needed files on disk."""
    if not CTC_LATEST.exists():
        asyncio.run(write_out(channel="UCC-UOdK8-mIjxBQm_ot1T-Q", video=""))


if __name__ == "__main__":
    initialize()
    if (found := asyncio.run(main())) is not None:
        print(
            f"The latest video {found.title} ({found.sudoku_link}) took "
            f"{time.strftime('%H:%M:%S', found.duration)}."
        )
