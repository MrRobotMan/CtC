"""Get the data on the latest cracking the cryptic video."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import dotenv

dotenv.load_dotenv()

from ctc import CTC_LATEST, CtcCurrent, Video, ctc_mainloop
from lmd import LMD_LATEST, Link, LmdCurrent, lmd_mainloop
from logger import LOGGER
from utils import read_data, BadVideoError


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
        ctc_video = Video.empty()
    lmd = read_data(LMD_LATEST)
    sandra_and_nala = Link.from_file(lmd.get("sandra and nala"))
    rat_run = Link.from_file(lmd.get("rat run"))
    LOGGER.debug(
        "ctc: %s, sandra & nala: %s, rat run: %s",
        ctc_video.title,
        sandra_and_nala.title,
        rat_run.title,
    )
    ctc = asyncio.create_task(ctc_mainloop(CtcCurrent(ctc_video, channel)))
    lmd = asyncio.create_task(lmd_mainloop(LmdCurrent(sandra_and_nala, rat_run)))
    await ctc
    await lmd


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(mainloop())
