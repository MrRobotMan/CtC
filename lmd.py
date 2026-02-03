from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from html.parser import HTMLParser
from pathlib import Path

import httpx

from logger import LOGGER
from utils import read_data, send_email, write_out

SANDRA_AND_NALA = "https://logic-masters.de/Raetselportal/Suche/erweitert.php?suchautor=SandraNala&suchverhalt=nichtgeloest"
RAT_RUN = "https://logic-masters.de/Raetselportal/Suche/erweitert.php?skname=x&suchtext=rat%20run&suchautor=marty_sears"
DAY = 60 * 60 * 24
LMD_LATEST = Path("lmd.json")
OK_RESPONSE = 200


async def lmd_mainloop(current: LmdCurrent) -> None:
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


@dataclass
class LmdCurrent:
    sandra_and_nala: Link
    rat_run: Link

    def update(self, item: Link, version: LogicMasters) -> None:
        match version:
            case LogicMasters.SANDRAANDNALA:
                self.sandra_and_nala = item
            case LogicMasters.RATRUN:
                self.rat_run = item
            case LogicMasters.NONE:
                return
        write_out(
            {
                "sandra and nala": self.sandra_and_nala.to_json(),
                "rat run": self.rat_run.to_json(),
            },
            LMD_LATEST,
        )


async def process_response(
    current: LmdCurrent, response: httpx.Response, lmd: LogicMasters
) -> None:
    if response.status_code == OK_RESPONSE:
        latest = get_latest(response.text)
        data = read_data(LMD_LATEST)
        LOGGER.debug("process_response - Latest: %s", latest)
        from_disk = Link.from_file(data.get(lmd.to_string()))
        LOGGER.debug("process_response - Stored: %s", from_disk)
        if latest != from_disk:
            LOGGER.debug("Emailing")
            string = lmd.to_string().title()
            current.update(latest, lmd)
            send_email(
                f"New {string} Sudoku: {latest.title}",
                f"Try the new {string} puzzle {latest.title}, https://logic-masters.de{latest.url}",
                "lmd",
            )


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
